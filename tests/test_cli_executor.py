from __future__ import annotations

import pytest

from app.tools.cli_executor import CLIExecutor, CLIResult


@pytest.mark.asyncio
async def test_fallback_rules(monkeypatch, cli_executor: CLIExecutor):
    calls: list[list[str]] = []

    async def fake_run(self, command, timeout_seconds, workspace):
        calls.append(command)
        if command[0] == "claude":
            return CLIResult(command[0], 1, "", "primary fail", command)
        return CLIResult(command[0], 0, "ok", "", command)

    monkeypatch.setattr(CLIExecutor, "_run_command", fake_run)

    result = await cli_executor.execute(
        prompt="fix bug",
        backend="claude",
        fallback_backend="codex",
        flags=[],
    )

    assert result.ok is True
    assert [c[0] for c in calls] == ["claude", "codex"]
