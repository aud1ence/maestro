from __future__ import annotations

from app.tools.github_client import GitHubClient


def test_issue_comment_token_takes_precedence():
    client = GitHubClient(
        api_base="https://api.github.com",
        default_token="default-token",
        issue_comment_token="issue-token",
        pull_request_token="pr-token",
    )

    headers = client._headers("issue_comment")
    assert headers["Authorization"] == "Bearer issue-token"


def test_pull_request_falls_back_to_default_token():
    client = GitHubClient(
        api_base="https://api.github.com",
        default_token="default-token",
        issue_comment_token=None,
        pull_request_token=None,
    )

    headers = client._headers("pull_request")
    assert headers["Authorization"] == "Bearer default-token"
