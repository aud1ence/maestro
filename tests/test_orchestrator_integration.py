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
        self.calls: list[tuple[str, str | None]] = []

    def ensure_synced(self, full_name: str, clone_url: str | None = None) -> Path:
        self.calls.append((full_name, clone_url))
        return self.path


def _make_payload(repo: str = "owner/repo", issue_id: int = 100, issue_number: int = 1, title: str = "Fix parser") -> dict:
    return {
        "action": "labeled",
        "issue": {
            "id": issue_id,
            "number": issue_number,
            "title": title,
            "body": "Details",
            "labels": [{"name": "agent"}],
        },
        "repository": {
            "full_name": repo,
            "clone_url": f"https://github.com/{repo}.git",
        },
        "sender": {"login": "alice"},
    }


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

    task, _ = engine.enqueue_from_webhook(_make_payload("alice/my-project"), "d1")
    final = await engine.process_task(task.id)

    assert final.state == TaskState.COMPLETED
    assert len(github.comments) == 1
    assert repo_manager.calls == [("alice/my-project", "https://github.com/alice/my-project.git")]


@pytest.mark.asyncio
async def test_different_repos_get_separate_workspaces(tmp_path: Path, app_config: AppConfig):
    store = TaskStore(tmp_path / "tasks.sqlite")
    synced: list[str] = []

    class TrackingRepoManager:
        def ensure_synced(self, full_name: str, clone_url: str | None = None) -> Path:
            synced.append(full_name)
            return tmp_path / full_name

    engine = OrchestratorEngine(
        store=store,
        config=app_config,
        cli_executor=StubCLI(CLIResult("claude", 0, "done", "", ["claude"])),
        agents=StubAgents(PipelineDecision.APPROVED),
        github_client=StubGitHub(),
        workspace_root=tmp_path,
        repo_manager=TrackingRepoManager(),
    )

    task_a, _ = engine.enqueue_from_webhook(_make_payload("alice/repo-a", issue_id=1), "d-a")
    task_b, _ = engine.enqueue_from_webhook(_make_payload("bob/repo-b", issue_id=2), "d-b")
    await engine.process_task(task_a.id)
    await engine.process_task(task_b.id)

    assert synced == ["alice/repo-a", "bob/repo-b"]


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

    task, _ = engine.enqueue_from_webhook(_make_payload(issue_id=101, issue_number=2, title="Fix lint"), "d2")
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
    engine = OrchestratorEngine(
        store=store,
        config=app_config,
        cli_executor=FallbackCLI(),
        agents=StubAgents(PipelineDecision.APPROVED),
        github_client=StubGitHub(),
        workspace_root=tmp_path,
        repo_manager=StubRepoManager(tmp_path / "repo"),
    )

    task, _ = engine.enqueue_from_webhook(_make_payload(issue_id=102, issue_number=3, title="Do fallback"), "d3")
    final = await engine.process_task(task.id)
    assert final.state == TaskState.COMPLETED


def test_webhook_without_agent_label_rejected(tmp_path: Path, app_config: AppConfig):
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
        "issue": {"id": 200, "number": 9, "title": "No label", "body": "", "labels": []},
        "repository": {"full_name": "anyone/any-repo"},
        "sender": {"login": "alice"},
    }

    with pytest.raises(ValueError, match="agent"):
        engine.enqueue_from_webhook(payload, "d-nolabel")
