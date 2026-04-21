from __future__ import annotations

from app.tools.github_client import GitHubClient


def test_token_in_auth_header():
    client = GitHubClient(api_base="https://api.github.com", token="my-pat")
    assert client._headers()["Authorization"] == "Bearer my-pat"


def test_no_auth_header_when_token_absent():
    client = GitHubClient(api_base="https://api.github.com", token=None)
    assert "Authorization" not in client._headers()
