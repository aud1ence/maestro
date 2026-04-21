from __future__ import annotations

import httpx


class GitHubClient:
    def __init__(
        self,
        *,
        api_base: str = "https://api.github.com",
        default_token: str | None = None,
        issue_comment_token: str | None = None,
        pull_request_token: str | None = None,
    ):
        self.default_token = default_token
        self.issue_comment_token = issue_comment_token
        self.pull_request_token = pull_request_token
        self.api_base = api_base.rstrip("/")

    def _token_for_scope(self, scope: str) -> str | None:
        if scope == "issue_comment":
            return self.issue_comment_token or self.default_token
        if scope == "pull_request":
            return self.pull_request_token or self.default_token
        return self.default_token

    def _headers(self, scope: str) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        token = self._token_for_scope(scope)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def comment_issue(self, repo_full_name: str, issue_number: int, body: str) -> None:
        url = f"{self.api_base}/repos/{repo_full_name}/issues/{issue_number}/comments"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=self._headers("issue_comment"), json={"body": body})
            response.raise_for_status()

    async def create_pull_request(
        self,
        repo_full_name: str,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = "main",
    ) -> dict:
        url = f"{self.api_base}/repos/{repo_full_name}/pulls"
        payload = {
            "title": title,
            "body": body,
            "head": head_branch,
            "base": base_branch,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=self._headers("pull_request"), json=payload)
            response.raise_for_status()
            return response.json()
