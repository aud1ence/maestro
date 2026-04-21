from __future__ import annotations

from typing import Protocol


class WikiContextProvider(Protocol):
    async def get_context(self, issue_title: str, issue_body: str) -> str:
        ...


class NullWikiContextProvider:
    async def get_context(self, issue_title: str, issue_body: str) -> str:
        return ""
