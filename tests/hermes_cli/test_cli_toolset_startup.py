"""CLI startup validates discovered plugins and keeps diagnostics out of JSONL."""

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


_REPO = Path(__file__).resolve().parents[2]


def _run_startup(tmp_path, body):
    # A fresh interpreter is essential: another test's discovery would mask the bug.
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.yaml").write_text("platforms:\n  a2a:\n    enabled: true\n", encoding="utf-8")
    env = {**os.environ, "HERMES_HOME": str(home), "PYTHONUTF8": "1"}
    code = textwrap.dedent("""\
        import cli
        from rich.console import Console
        from tools.registry import registry
        from toolsets import resolve_toolset, validate_toolset

        instance = cli.HermesCLI.__new__(cli.HermesCLI)
        instance.console = Console()
        cli.CLI_CONFIG = {"agent": {"disabled_toolsets": ["web"]},
                          "mcp_servers": {"configured_mcp": {}}}
    """) + textwrap.dedent(body)
    return subprocess.run([sys.executable, "-c", code], cwd=_REPO, env=env,
                          capture_output=True, text=True, encoding="utf-8", timeout=60)


def test_cli_discovers_plugin_toolsets_before_validation(tmp_path):
    result = _run_startup(tmp_path, """\
        from hermes_cli.plugins import get_plugin_manager

        requested = ["a2a", "terminal", "configured_mcp"]
        instance._init_toolsets(requested)
        assert validate_toolset("a2a")
        tools = resolve_toolset("a2a")
        assert tools
        assert all(registry.get_entry(name).check_fn() for name in tools)
        assert get_plugin_manager()._plugins["a2a-platform"].deferred
        assert instance.enabled_toolsets == requested
        assert instance.disabled_toolsets == ["web"]
    """)
    assert result.returncode == 0, result.stderr
    assert "Unknown toolsets" not in result.stdout + result.stderr


@pytest.mark.parametrize("stream_json", [False, True])
def test_unknown_toolset_warning_stays_visible_off_stdout(tmp_path, stream_json):
    body = textwrap.dedent("""\
        requested = ["terminal", "configured_mcp", "not_a_real_toolset"]
        instance._init_toolsets(requested)
        assert instance.enabled_toolsets == requested
        assert instance.disabled_toolsets == ["web"]
    """)
    if stream_json:
        body += textwrap.dedent("""\
            from hermes_cli.stream_json import StreamJsonEmitter
            emitter = StreamJsonEmitter(model="test-model", session_id="test-session")
            assert emitter.emit_result({"final_response": "ok"}) == 0
        """)
    else:
        body += 'print("ordinary output")\n'
    result = _run_startup(tmp_path, body)
    assert result.returncode == 0, result.stderr
    assert "Warning: Unknown toolsets: not_a_real_toolset" in result.stderr
    assert "configured_mcp" not in result.stderr
    if stream_json:
        events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        assert [event["type"] for event in events] == ["system", "result"]
        assert events[0]["subtype"] == "init"
        assert events[-1]["exit_code"] == 0 and events[-1]["text"] == "ok"
    else:
        assert result.stdout.strip() == "ordinary output"
