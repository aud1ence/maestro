from __future__ import annotations

import httpx


class GitHubClient:
    def __init__(self, *, api_base: str = "https://api.github.com", token: str | None = None):
        self.token = token
        self.api_base = api_base.rstrip("/")

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def comment_issue(self, repo_full_name: str, issue_number: int, body: str) -> None:
        url = f"{self.api_base}/repos/{repo_full_name}/issues/{issue_number}/comments"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=self._headers(), json={"body": body})
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
            response = await client.post(url, headers=self._headers(), json=payload)
            response.raise_for_status()
            return response.json()
