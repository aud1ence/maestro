from __future__ import annotations

from pydantic import BaseModel, Field

from app.config import AppConfig
from app.schemas import PipelineDecision


class PlannerOutput(BaseModel):
    summary: str
    coding_prompt: str
    risk_level: str = "medium"


class ReviewOutput(BaseModel):
    decision: PipelineDecision
    summary: str
    issues: list[str] = Field(default_factory=list)


def _parse_decision(text: str) -> PipelineDecision:
    upper = text.upper()
    if "CHANGES_REQUESTED" in upper:
        return PipelineDecision.CHANGES_REQUESTED
    if "NEEDS_HUMAN" in upper:
        return PipelineDecision.NEEDS_HUMAN
    if "APPROVED" in upper:
        return PipelineDecision.APPROVED
    return PipelineDecision.APPROVED


class AgentsFacade:
    """Role runner: each role delegates to its configured CLI backend.

    No LLM agents or system prompts — all intelligence comes from the CLI tools.
    Role → CLI backend mapping is driven by config.roles.
    """

    def __init__(self, config: AppConfig, cli_executor):
        self.config = config
        self.cli = cli_executor

    async def plan(self, issue_title: str, issue_body: str, extra_context: str = "") -> PlannerOutput:
        role = self.config.roles.planner
        prompt = (
            "Decompose this GitHub issue into a single, precise coding prompt.\n"
            "Output the coding prompt only — no extra commentary.\n"
            f"Title: {issue_title}\n"
            f"Body: {issue_body}\n"
        )
        if extra_context:
            prompt += f"Context:\n{extra_context}\n"

        result = await self.cli.execute(
            prompt=prompt,
            backend=role.backend,
            fallback_backend=role.fallback_backend,
            flags=role.flags,
        )

        coding_prompt = result.stdout.strip() or f"Implement GitHub issue: {issue_title}\n\n{issue_body}"
        return PlannerOutput(summary=issue_title, coding_prompt=coding_prompt)

    async def review(self, task_summary: str, coding_stdout: str, coding_stderr: str) -> ReviewOutput:
        role = self.config.roles.reviewer
        prompt = (
            "Review this coding result. "
            "Output exactly one of: APPROVED, CHANGES_REQUESTED, or NEEDS_HUMAN "
            "on the first line, followed by a brief reason.\n"
            f"Task: {task_summary}\n"
            f"Output:\n{coding_stdout}\n"
            f"Errors:\n{coding_stderr}\n"
        )

        result = await self.cli.execute(
            prompt=prompt,
            backend=role.backend,
            fallback_backend=role.fallback_backend,
            flags=role.flags,
        )

        if not result.ok and not result.stdout.strip():
            return ReviewOutput(
                decision=PipelineDecision.CHANGES_REQUESTED,
                summary=f"Reviewer CLI failed (exit {result.returncode}).",
                issues=[result.stderr[:300]],
            )

        decision = _parse_decision(result.stdout)
        return ReviewOutput(decision=decision, summary=(result.stdout or "No output from reviewer")[:500])
