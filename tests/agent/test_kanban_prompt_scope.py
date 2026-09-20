"""Worker prompt identity follows task ownership, not Kanban tool availability."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agent.agent_init import _load_tools
from agent.delegation_context import (
    DELEGATED_CHILD_ENV_MARKER,
    delegated_child_context,
    non_dispatcher_owned_context,
)
from agent.prompt_builder import KANBAN_GUIDANCE
from agent.system_prompt import _tool_guidance_block


def _agent(initialization, tool_available=True):
    names = {"kanban_show"} if tool_available else {"terminal"}
    agent = SimpleNamespace(valid_tool_names=names, quiet_mode=True)
    if initialization == "load_tools":
        schemas = [{"function": {"name": name}} for name in names]
        # Only discovery is synthetic: exercise the real startup and prompt paths
        # without plugins, provider calls, persisted memory, or a live board.
        with patch("hermes_cli.plugins.discover_plugins"), patch(
            "model_tools.get_tool_definitions", return_value=schemas
        ):
            _load_tools(agent, ["kanban"], None)
    return agent


@pytest.mark.parametrize("initialization", ["load_tools", "prompt_fallback"])
@pytest.mark.parametrize("tool_available", [True, False])
@pytest.mark.parametrize(
    "scope,task,owns_task",
    [
        ("ordinary", None, False),
        ("ordinary", "", False),
        ("ordinary", "   ", False),
        ("worker", "t_fixture", True),
        ("child", "t_fixture", False),
        ("non-owner", "t_fixture", False),
        ("child-process", "t_fixture", False),
    ],
)
def test_only_task_owner_receives_worker_guidance(
    monkeypatch, initialization, tool_available, scope, task, owns_task
):
    monkeypatch.delenv("HERMES_KANBAN_TASK", raising=False)
    monkeypatch.delenv(DELEGATED_CHILD_ENV_MARKER, raising=False)
    if task is not None:
        monkeypatch.setenv("HERMES_KANBAN_TASK", task)
    if scope == "child-process":
        monkeypatch.setenv(DELEGATED_CHILD_ENV_MARKER, "1")
    context = {
        "child": delegated_child_context,
        "non-owner": non_dispatcher_owned_context,
    }.get(scope, nullcontext)
    with context():
        agent = _agent(initialization, tool_available)
        guidance = _tool_guidance_block(agent) or ""
    assert (KANBAN_GUIDANCE in guidance) is (owns_task and tool_available)


# Upstream freezes the guidance snapshot only on the load_tools path; the prompt_fallback path is
# re-resolved per build and is not memoized, so it is not covered here.
@pytest.mark.parametrize("initialization", ["load_tools"])
@pytest.mark.parametrize("child_scope", [delegated_child_context, non_dispatcher_owned_context])
def test_guidance_snapshot_stays_per_agent_across_context_changes(
    monkeypatch, initialization, child_scope
):
    monkeypatch.delenv("HERMES_KANBAN_TASK", raising=False)
    monkeypatch.delenv(DELEGATED_CHILD_ENV_MARKER, raising=False)
    ordinary = _agent(initialization)
    ordinary_prompt = _tool_guidance_block(ordinary)
    assert not ordinary_prompt

    monkeypatch.setenv("HERMES_KANBAN_TASK", "t_fixture")
    worker = _agent(initialization)
    worker_prompt = _tool_guidance_block(worker)
    assert KANBAN_GUIDANCE in worker_prompt
    with child_scope():
        child = _agent(initialization)
        child_prompt = _tool_guidance_block(child)
        assert not child_prompt
        assert _tool_guidance_block(worker) == worker_prompt
        assert _tool_guidance_block(ordinary) == ordinary_prompt

    assert _tool_guidance_block(child) == child_prompt
    assert _tool_guidance_block(worker) == worker_prompt
    monkeypatch.delenv("HERMES_KANBAN_TASK")
    assert _tool_guidance_block(worker) == worker_prompt
    assert _tool_guidance_block(ordinary) == ordinary_prompt
