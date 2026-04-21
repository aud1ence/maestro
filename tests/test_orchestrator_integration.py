from __future__ import annotations

from pathlib import Path

import pytest

from app.agents import PlannerOutput, ReviewOutput
from app.config import AppConfig, OrchestratorConfig
from app.orchestrator import OrchestratorEngine
from app.schemas import PipelineDecision, TaskState
from app.store import TaskStore
from app.tools.cli_executor import CLIResult


class StubCLI:
    def __init__(self, result: CLIResult):
        self.result = result

    async def execute(self, **kwargs):
        return self.result


class StubAgents:
    def __init__(self, review_decision: PipelineDecision):
        self.review_decision = review_decision

    async def plan(self, issue_title, issue_body, extra_context=""):
        return PlannerOutput(summary=issue_title, coding_prompt=f"do: {issue_title}")

    async def review(self, task_summary, coding_stdout, coding_stderr):
        return ReviewOutput(decision=self.review_decision, summary="review done", issues=[])


class StubGitHub:
    def __init__(self):
        self.comments = []

    async def comment_issue(self, repo_full_name, issue_number, body):
        self.comments.append((repo_full_name, issue_number, body))


class StubRepoManager:
    def __init__(self, path: Path):
        self.path = path
        self.calls = []

    def ensure_synced(self, clone_url: str, local_relative_path: str) -> Path:
        self.calls.append((clone_url, local_relative_path))
        return self.path


@pytest.mark.asyncio
async def test_happy_path_to_completed(tmp_path: Path, app_config: AppConfig):
    store = TaskStore(tmp_path / "tasks.sqlite")
    github = StubGitHub()
    repo_manager = StubRepoManager(tmp_path / "repo")
    engine = OrchestratorEngine(
        store=store,
        config=app_config,
        cli_executor=StubCLI(CLIResult("claude", 0, "done", "", ["claude"])),
        agents=StubAgents(PipelineDecision.APPROVED),
        github_client=github,
        workspace_root=tmp_path,
        repo_manager=repo_manager,
    )

    payload = {
        "action": "labeled",
        "issue": {
            "id": 100,
            "number": 1,
            "title": "Fix parser",
            "body": "Please fix",
            "labels": [{"name": "agent"}],
        },
        "repository": {"full_name": "aud1ence/obsidian-wiki-mcp"},
        "sender": {"login": "alice"},
    }
    task, _ = engine.enqueue_from_webhook(payload, "d1")

    final = await engine.process_task(task.id)

    assert final.state == TaskState.COMPLETED
    assert len(github.comments) == 1
    assert len(repo_manager.calls) == 1


@pytest.mark.asyncio
async def test_reviewer_reject_over_threshold_goes_needs_human(tmp_path: Path, app_config: AppConfig):
    store = TaskStore(tmp_path / "tasks.sqlite")
    github = StubGitHub()
    strict_config = app_config.model_copy(
        update={"orchestrator": OrchestratorConfig(max_retries=2, reviewer_changes_threshold=0)}
    )
    engine = OrchestratorEngine(
        store=store,
        config=strict_config,
        cli_executor=StubCLI(CLIResult("claude", 0, "done", "", ["claude"])),
        agents=StubAgents(PipelineDecision.CHANGES_REQUESTED),
        github_client=github,
        workspace_root=tmp_path,
        repo_manager=StubRepoManager(tmp_path / "repo"),
    )

    payload = {
        "action": "labeled",
        "issue": {
            "id": 101,
            "number": 2,
            "title": "Fix lint",
            "body": "Please fix lint",
            "labels": [{"name": "agent"}],
        },
        "repository": {"full_name": "aud1ence/obsidian-wiki-mcp"},
        "sender": {"login": "alice"},
    }
    task, _ = engine.enqueue_from_webhook(payload, "d2")

    final = await engine.process_task(task.id)

    assert final.state == TaskState.NEEDS_HUMAN


@pytest.mark.asyncio
async def test_claude_fail_codex_fallback_via_stub(tmp_path: Path, app_config: AppConfig):
    class FallbackCLI:
        async def execute(self, **kwargs):
            assert kwargs["backend"] == "claude"
            assert kwargs["fallback_backend"] == "codex"
            return CLIResult("codex", 0, "fallback ok", "", ["codex"])

    store = TaskStore(tmp_path / "tasks.sqlite")
    github = StubGitHub()
    engine = OrchestratorEngine(
        store=store,
        config=app_config,
        cli_executor=FallbackCLI(),
        agents=StubAgents(PipelineDecision.APPROVED),
        github_client=github,
        workspace_root=tmp_path,
        repo_manager=StubRepoManager(tmp_path / "repo"),
    )

    payload = {
        "action": "labeled",
        "issue": {
            "id": 102,
            "number": 3,
            "title": "Do fallback",
            "body": "Ensure fallback",
            "labels": [{"name": "agent"}],
        },
        "repository": {"full_name": "aud1ence/obsidian-wiki-mcp"},
        "sender": {"login": "alice"},
    }
    task, _ = engine.enqueue_from_webhook(payload, "d3")

    final = await engine.process_task(task.id)
    assert final.state == TaskState.COMPLETED


def test_reject_non_target_repo(tmp_path: Path, app_config: AppConfig):
    store = TaskStore(tmp_path / "tasks.sqlite")
    engine = OrchestratorEngine(
        store=store,
        config=app_config,
        cli_executor=StubCLI(CLIResult("claude", 0, "", "", ["claude"])),
        agents=StubAgents(PipelineDecision.APPROVED),
        github_client=StubGitHub(),
        workspace_root=tmp_path,
        repo_manager=StubRepoManager(tmp_path / "repo"),
    )

    payload = {
        "action": "labeled",
        "issue": {
            "id": 103,
            "number": 4,
            "title": "Nope",
            "body": "Wrong repo",
            "labels": [{"name": "agent"}],
        },
        "repository": {"full_name": "someone/else"},
        "sender": {"login": "alice"},
    }

    with pytest.raises(ValueError):
        engine.enqueue_from_webhook(payload, "d4")
