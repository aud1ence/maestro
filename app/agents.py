from __future__ import annotations

import os

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


class AgentsFacade:
    def __init__(self, config: AppConfig):
        self.config = config
        self._sdk_available = False
        self._planner_agent = None
        self._reviewer_agent = None
        self._runner = None

        if config.use_openai_sdk and os.getenv("OPENAI_API_KEY"):
            self._init_sdk_agents()

    def _init_sdk_agents(self) -> None:
        try:
            from agents import Agent, Runner
        except Exception:
            return

        self._planner_agent = Agent(
            name="Planner Agent",
            instructions=self.config.prompts.planner_system,
            output_type=PlannerOutput,
        )
        self._reviewer_agent = Agent(
            name="Reviewer Agent",
            instructions=self.config.prompts.reviewer_system,
            output_type=ReviewOutput,
        )
        self._runner = Runner
        self._sdk_available = True

    async def plan(self, issue_title: str, issue_body: str, extra_context: str = "") -> PlannerOutput:
        prompt = (
            "Break this issue into a coding task and return concise plan output.\n"
            f"Title: {issue_title}\n"
            f"Body: {issue_body}\n"
            f"Context: {extra_context}\n"
        )

        if self._sdk_available and self._planner_agent and self._runner:
            result = await self._runner.run(self._planner_agent, prompt)
            return result.final_output_as(PlannerOutput)

        summary = issue_title.strip() or "Implement issue"
        coding_prompt = f"Implement GitHub issue: {issue_title}\n\n{issue_body}".strip()
        return PlannerOutput(summary=summary, coding_prompt=coding_prompt)

    async def review(self, task_summary: str, coding_stdout: str, coding_stderr: str) -> ReviewOutput:
        prompt = (
            "Review this coding result and decide APPROVED, CHANGES_REQUESTED, or NEEDS_HUMAN.\n"
            f"Task: {task_summary}\n"
            f"STDOUT:\n{coding_stdout}\n"
            f"STDERR:\n{coding_stderr}\n"
        )

        if self._sdk_available and self._reviewer_agent and self._runner:
            result = await self._runner.run(self._reviewer_agent, prompt)
            return result.final_output_as(ReviewOutput)

        if coding_stderr.strip():
            return ReviewOutput(
                decision=PipelineDecision.CHANGES_REQUESTED,
                summary="CLI execution has stderr output; changes requested.",
                issues=[coding_stderr.strip()[:200]],
            )

        return ReviewOutput(
            decision=PipelineDecision.APPROVED,
            summary="Execution completed without errors.",
            issues=[],
        )
