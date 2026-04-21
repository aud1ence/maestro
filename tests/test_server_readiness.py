from __future__ import annotations

from app.config import AppConfig
from app.server import _check_claude_auth, _check_codex_auth, _github_auth_readiness


def test_check_claude_auth_reports_logged_out(monkeypatch):
    monkeypatch.setattr("app.server._run_auth_status", lambda command: (1, '{"loggedIn": false}'))
    result = _check_claude_auth()
    assert result["installed"] is True
    assert result["authenticated"] is False
    assert result["login_command"] == "claude auth login"


def test_check_codex_auth_reports_logged_in(monkeypatch):
    monkeypatch.setattr("app.server._run_auth_status", lambda command: (0, "Logged in using ChatGPT"))
    result = _check_codex_auth()
    assert result["installed"] is True
    assert result["authenticated"] is True


def test_github_auth_readiness_by_role(monkeypatch):
    monkeypatch.setenv("GITHUB_ISSUE_TOKEN", "issue")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_PR_TOKEN", raising=False)
    result = _github_auth_readiness(AppConfig())
    assert result["issue_comment_token_configured"] is True
    assert result["pull_request_token_configured"] is False
