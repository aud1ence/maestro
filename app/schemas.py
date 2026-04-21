from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskState(str, Enum):
    QUEUED = "queued"
    PLANNING = "planning"
    CODING = "coding"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_HUMAN = "needs_human"


class PipelineDecision(str, Enum):
    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    NEEDS_HUMAN = "NEEDS_HUMAN"


class ExecutionConfig(BaseModel):
    backend: str = "claude"
    fallback_backend: str = "codex"
    flags: list[str] = Field(default_factory=list)
    verify_commands: list[str] = Field(default_factory=list)
    skill: str = "default"
    risk_level: str = "medium"


class WebhookIssue(BaseModel):
    id: int
    number: int
    title: str
    body: str | None = ""


class WebhookRepository(BaseModel):
    full_name: str
    clone_url: str | None = None


class WebhookSender(BaseModel):
    login: str


class GitHubWebhookPayload(BaseModel):
    action: str
    issue: WebhookIssue
    repository: WebhookRepository
    sender: WebhookSender
    labels: list[str] = Field(default_factory=list)

    @classmethod
    def from_raw(cls, payload: dict[str, Any]) -> "GitHubWebhookPayload":
        labels = [item["name"] for item in payload.get("issue", {}).get("labels", [])]
        return cls(
            action=payload.get("action", ""),
            issue=WebhookIssue(
                id=payload["issue"]["id"],
                number=payload["issue"]["number"],
                title=payload["issue"]["title"],
                body=payload["issue"].get("body") or "",
            ),
            repository=WebhookRepository(
                full_name=payload["repository"]["full_name"],
                clone_url=payload["repository"].get("clone_url"),
            ),
            sender=WebhookSender(login=payload["sender"]["login"]),
            labels=labels,
        )


class TaskResponse(BaseModel):
    id: str
    state: TaskState
    retry_count: int
    idempotency_key: str
    last_error: str | None = None
    result_summary: str | None = None
