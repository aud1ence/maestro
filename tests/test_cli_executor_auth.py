from __future__ import annotations

from pathlib import Path

from app.config import PolicyConfig
from app.policy import PolicyGuard
from app.tools.cli_executor import CLIExecutor


def test_claude_auth_hint_is_appended_on_not_logged_in(tmp_path: Path):
    guard = PolicyGuard(PolicyConfig(allowed_commands=["claude"], allowed_paths=[]), tmp_path)
    executor = CLIExecutor(guard, tmp_path)

    stderr = executor._with_auth_hint(
        backend="claude",
        stdout="",
        stderr="Not logged in · Please run /login",
        returncode=1,
    )

    assert "claude auth login" in stderr


def test_codex_auth_hint_is_appended_on_login_error(tmp_path: Path):
    guard = PolicyGuard(PolicyConfig(allowed_commands=["codex"], allowed_paths=[]), tmp_path)
    executor = CLIExecutor(guard, tmp_path)

    stderr = executor._with_auth_hint(
        backend="codex",
        stdout="Error: Please run codex login",
        stderr="",
        returncode=1,
    )

    assert "codex login --device-auth" in stderr
