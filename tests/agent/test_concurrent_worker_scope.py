"""Concurrent worker, ordinary, and delegated-child identity boundaries."""

from __future__ import annotations

import json
import asyncio
import os
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agent.agent_init import _load_tools
from agent.delegation_context import (
    DELEGATED_CHILD_ENV_MARKER,
    delegated_child_context,
    delegated_child_subprocess_env,
    non_dispatcher_owned_context,
)
from agent.prompt_builder import KANBAN_GUIDANCE
from agent.system_prompt import _tool_guidance_block


@pytest.fixture()
def worker_environment(monkeypatch, tmp_path):
    """A task-local fixture; no concurrent test changes process-global env."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "worker-home"))
    monkeypatch.setenv("HERMES_KANBAN_TASK", "worker-task")
    monkeypatch.setenv("HERMES_KANBAN_DB", str(tmp_path / "worker-home" / "kanban.db"))
    monkeypatch.delenv(DELEGATED_CHILD_ENV_MARKER, raising=False)
    return tmp_path


def _startup_agent():
    names = {"kanban_show"}
    agent = SimpleNamespace(valid_tool_names=names, quiet_mode=True)
    _load_tools(agent, ["kanban"], None)
    return agent


@pytest.mark.parametrize("round_number", range(5))
def test_overlapping_real_startup_scopes_keep_worker_guidance_only_for_worker(
    worker_environment,
    round_number,
):
    """Three simultaneous real startup/prompt resolutions keep identity separate."""
    barrier = threading.Barrier(3)
    seen = {}
    errors = []

    def run(name, context):
        try:
            with context:
                barrier.wait(timeout=10)
                agent = _startup_agent()
                frozen = _tool_guidance_block(agent) or ""
                seen[name] = KANBAN_GUIDANCE in frozen
                barrier.wait(timeout=10)
            # An agent retains its original role after another thread exits a scope.
            assert (_tool_guidance_block(agent) or "") == frozen
        except BaseException as exc:  # surface worker failures in the main test
            errors.append(exc)

    with patch("hermes_cli.plugins.discover_plugins"), patch(
        "model_tools.get_tool_definitions",
        return_value=[{"function": {"name": "kanban_show"}}],
    ):
        # The worker has no scope wrapper; its environment is the worker identity.
        threads = [
            threading.Thread(target=run, args=("worker", _NoopContext())),
            threading.Thread(target=run, args=("ordinary", non_dispatcher_owned_context())),
            threading.Thread(target=run, args=("child", delegated_child_context("child-session"))),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

    assert not any(thread.is_alive() for thread in threads)
    assert not errors
    assert seen == {"worker": True, "ordinary": False, "child": False}


@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
def test_child_session_and_identity_contexts_restore_after_exception(worker_environment, failure):
    from gateway.session_context import get_session_env
    from agent.delegation_context import is_dispatcher_owned_worker_context

    baseline_session = get_session_env("HERMES_SESSION_ID")
    assert is_dispatcher_owned_worker_context() is True
    with pytest.raises(failure):
        with delegated_child_context("child-session"):
            assert is_dispatcher_owned_worker_context() is False
            assert get_session_env("HERMES_SESSION_ID") == "child-session"
            raise failure("cancelled child")
    assert is_dispatcher_owned_worker_context() is True
    assert get_session_env("HERMES_SESSION_ID") == baseline_session


def test_child_cannot_mutate_parent_board_through_real_mutation_fence(worker_environment):
    from hermes_cli import kanban_db

    board = Path(os.environ["HERMES_KANBAN_DB"])
    with delegated_child_context("child-session"):
        child_env = delegated_child_subprocess_env(dict(os.environ))
        assert "HERMES_KANBAN_TASK" not in child_env
        assert child_env[DELEGATED_CHILD_ENV_MARKER]
        assert child_env["HERMES_HOME"] == os.environ["HERMES_HOME"]
        with pytest.raises(PermissionError, match="cannot mutate Kanban"):
            kanban_db._assert_not_delegated_child_mutation(board)

    # The same supported guard remains open to the dispatcher-owned worker.
    kanban_db._assert_not_delegated_child_mutation(board)


@pytest.mark.parametrize("second_is_child", [False, True])
def test_subprocess_fixtures_keep_home_and_task_identity_independent(tmp_path, second_is_child):
    script = r'''
import json, os, sys
from types import SimpleNamespace
from unittest.mock import patch
from agent.agent_init import _load_tools
from agent.prompt_builder import KANBAN_GUIDANCE
from agent.system_prompt import _tool_guidance_block

with patch("hermes_cli.plugins.discover_plugins"), patch(
    "model_tools.get_tool_definitions",
    return_value=[{"function": {"name": "kanban_show"}}],
):
    agent = SimpleNamespace(valid_tool_names={"kanban_show"}, quiet_mode=True)
    _load_tools(agent, ["kanban"], None)
    frozen = _tool_guidance_block(agent) or ""
    print("READY", flush=True)
    assert sys.stdin.readline().strip() == "go"
    os.environ["HERMES_KANBAN_TASK"] += "-changed"
    assert (_tool_guidance_block(agent) or "") == frozen
    print(json.dumps({
        "home": os.environ.get("HERMES_HOME"),
        "task": os.environ.get("HERMES_KANBAN_TASK"),
        "child": os.environ.get("HERMES_DELEGATED_CHILD_CONTEXT"),
        "guidance": KANBAN_GUIDANCE in (_tool_guidance_block(agent) or ""),
    }))
'''
    python = os.environ.get("HERMES_PYTHON", sys.executable)
    common = os.environ.copy()
    common.pop("HERMES_KANBAN_TASK", None)
    common.pop(DELEGATED_CHILD_ENV_MARKER, None)
    common["PYTHONPATH"] = str(Path(__file__).parents[2])
    envs = []
    for label in ("one", "two"):
        env = common.copy()
        env["HERMES_HOME"] = str(tmp_path / f"home-{label}")
        env["HERMES_KANBAN_TASK"] = f"task-{label}"
        if label == "two" and second_is_child:
            env[DELEGATED_CHILD_ENV_MARKER] = str(tmp_path / f"home-{label}")
        envs.append(env)

    with subprocess.Popen(
        [python, "-c", script], cwd=str(Path(__file__).parents[2]),
        env=envs[0], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ) as first, subprocess.Popen(
        [python, "-c", script], cwd=str(Path(__file__).parents[2]),
        env=envs[1], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ) as second:
        # Both actual subprocesses have captured independent context before release.
        for process in (first, second):
            import queue
            ready = queue.Queue()
            reader = threading.Thread(target=lambda p=process, q=ready: q.put(p.stdout.readline()), daemon=True)
            reader.start()
            try:
                line = ready.get(timeout=30)
            except queue.Empty:
                process.kill()
                raise AssertionError("fixture subprocess never reached readiness barrier")
            assert line.strip() == "READY"
        for process in (first, second):
            process.stdin.write("go\n")
            process.stdin.flush()
        outputs = []
        for process in (first, second):
            stdout, stderr = process.communicate(timeout=60)
            assert process.returncode == 0, stderr
            outputs.append(json.loads(stdout.strip().splitlines()[-1]))

    assert outputs == [
        {"home": str(tmp_path / "home-one"), "task": "task-one-changed", "child": None, "guidance": True},
        {"home": str(tmp_path / "home-two"), "task": "task-two-changed", "child": str(tmp_path / "home-two") if second_is_child else None, "guidance": not second_is_child},
    ]


class _NoopContext:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False
