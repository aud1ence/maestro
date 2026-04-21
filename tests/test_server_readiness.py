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


def test_github_auth_readiness_configured(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    result = _github_auth_readiness(AppConfig())
    assert result["configured"] is True
    assert result["token_env"] == "GITHUB_TOKEN"


def test_github_auth_readiness_not_configured(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    result = _github_auth_readiness(AppConfig())
    assert result["configured"] is False
