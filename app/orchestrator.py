from __future__ import annotations

import logging
import subprocess
import uuid
from pathlib import Path
from typing import Any

from app.agents import AgentsFacade
from app.config import AppConfig
from app.schemas import PipelineDecision, TaskState
from app.store import TaskRecord, TaskStore
from app.tools.cli_executor import CLIExecutor
from app.tools.github_client import GitHubClient
from app.tools.repo_workspace import RepoWorkspaceManager
from app.tools.wiki_context import NullWikiContextProvider, WikiContextProvider

logger = logging.getLogger(__name__)


class OrchestratorEngine:
    def __init__(
        self,
        *,
        store: TaskStore,
        config: AppConfig,
        cli_executor: CLIExecutor,
        agents: AgentsFacade,
        github_client: GitHubClient,
        workspace_root: Path,
        wiki_context: WikiContextProvider | None = None,
        repo_manager: RepoWorkspaceManager | None = None,
    ):
        self.store = store
        self.config = config
        self.cli_executor = cli_executor
        self.agents = agents
        self.github_client = github_client
        self.workspace_root = workspace_root
        self.wiki_context = wiki_context or NullWikiContextProvider()
        self.repo_manager = repo_manager or RepoWorkspaceManager(workspace_root)

    def enqueue_from_webhook(self, payload: dict[str, Any], delivery_id: str) -> tuple[TaskRecord, bool]:
        issue = payload["issue"]
        labels = {label["name"] for label in issue.get("labels", [])}
        if "agent" not in labels:
            raise ValueError("Issue is not labeled with 'agent'")

        repo_name = payload["repository"]["full_name"]
        if repo_name != self.config.repo.target_full_name:
            raise ValueError(f"Repository not allowed: {repo_name}")

        idempotency_key = f"{delivery_id}:{issue['id']}:{payload.get('action','')}"
        task_id = str(uuid.uuid5(uuid.NAMESPACE_URL, idempotency_key))
        return self.store.create_task_if_absent(task_id, idempotency_key, payload)

    async def process_task(self, task_id: str) -> TaskRecord:
        task = self.store.get_task(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")

        issue = task.payload["issue"]
        repo = task.payload["repository"]
        issue_title = issue["title"]
        issue_body = issue.get("body") or ""

        task_workspace = self.workspace_root
        if self.config.repo.sync_on_task:
            logger.info("task=%s syncing repo=%s", task_id, self.config.repo.target_full_name)
            task_workspace = self.repo_manager.ensure_synced(
                clone_url=self.config.repo.clone_url,
                local_relative_path=self.config.repo.local_path,
            )

        logger.info("task=%s state=planning", task_id)
        self.store.transition_state(task_id, TaskState.PLANNING)
        context = await self.wiki_context.get_context(issue_title, issue_body)
        plan = await self.agents.plan(issue_title, issue_body, context)

        logger.info("task=%s state=coding", task_id)
        self.store.transition_state(task_id, TaskState.CODING)
        coding_result = await self.cli_executor.execute(
            prompt=plan.coding_prompt,
            backend=self.config.execution.backend,
            fallback_backend=self.config.execution.fallback_backend,
            flags=self.config.execution.flags,
            workspace=task_workspace,
        )

        verify_failure = self._run_verify_commands(task_workspace)
        if verify_failure:
            coding_result.stderr = f"{coding_result.stderr}\n{verify_failure}".strip()

        logger.info("task=%s state=reviewing", task_id)
        self.store.transition_state(task_id, TaskState.REVIEWING)
        review = await self.agents.review(
            task_summary=plan.summary,
            coding_stdout=coding_result.stdout,
            coding_stderr=coding_result.stderr,
        )

        if review.decision == PipelineDecision.APPROVED:
            summary = "Approved and ready for PR"
            self.store.transition_state(task_id, TaskState.COMPLETED, result_summary=summary)
            await self.github_client.comment_issue(
                repo_full_name=repo["full_name"],
                issue_number=issue["number"],
                body=f"Agent completed task `{task_id}`: {review.summary}",
            )
            return self.store.get_task(task_id)  # type: ignore[return-value]

        if review.decision == PipelineDecision.CHANGES_REQUESTED:
            task = self.store.get_task(task_id)
            assert task is not None
            if task.retry_count >= self.config.orchestrator.reviewer_changes_threshold:
                reason = "Reviewer requested changes beyond retry threshold"
                self.store.transition_state(task_id, TaskState.NEEDS_HUMAN, last_error=reason)
                await self.github_client.comment_issue(
                    repo_full_name=repo["full_name"],
                    issue_number=issue["number"],
                    body=f"Agent paused task `{task_id}`: {reason}",
                )
                return self.store.get_task(task_id)  # type: ignore[return-value]

            self.store.transition_state(
                task_id,
                TaskState.CODING,
                last_error="Reviewer requested changes",
                increment_retry=True,
            )
            self.store.transition_state(task_id, TaskState.REVIEWING)
            self.store.transition_state(task_id, TaskState.NEEDS_HUMAN, last_error="Manual intervention required")
            return self.store.get_task(task_id)  # type: ignore[return-value]

        reason = "Reviewer marked as needs_human"
        self.store.transition_state(task_id, TaskState.NEEDS_HUMAN, last_error=reason)
        await self.github_client.comment_issue(
            repo_full_name=repo["full_name"],
            issue_number=issue["number"],
            body=f"Agent requires manual help for task `{task_id}`: {review.summary}",
        )
        return self.store.get_task(task_id)  # type: ignore[return-value]

    def retry_task(self, task_id: str) -> TaskRecord:
        task = self.store.reset_for_retry(task_id)
        return task

    def _run_verify_commands(self, workspace: Path) -> str | None:
        for cmd in self.config.execution.verify_commands:
            completed = subprocess.run(
                ["bash", "-lc", cmd],
                cwd=workspace,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                return f"Verify command failed: {cmd}\n{completed.stdout}\n{completed.stderr}".strip()
        return None
