from __future__ import annotations

import hashlib
import hmac
import logging
import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request

from app.agents import AgentsFacade
from app.config import AppConfig, load_config
from app.orchestrator import OrchestratorEngine
from app.policy import PolicyGuard
from app.schemas import TaskResponse
from app.store import TaskStore
from app.tools.cli_executor import CLIExecutor
from app.tools.github_client import GitHubClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


class AppContainer:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.config: AppConfig = load_config(workspace_root / "config" / "agent.yaml")
        db_path = workspace_root / "data" / "tasks.sqlite"
        self.store = TaskStore(db_path)
        self.policy_guard = PolicyGuard(self.config.policy, workspace_root)
        self.cli_executor = CLIExecutor(self.policy_guard, workspace_root)
        self.agents = AgentsFacade(self.config)
        self.github_client = GitHubClient(
            token=os.getenv("GITHUB_TOKEN"),
            api_base=self.config.github_api_base,
        )
        self.engine = OrchestratorEngine(
            store=self.store,
            config=self.config,
            cli_executor=self.cli_executor,
            agents=self.agents,
            github_client=self.github_client,
            workspace_root=workspace_root,
        )


def create_app(workspace_root: Path | None = None) -> FastAPI:
    root = workspace_root or Path(__file__).resolve().parents[1]
    container = AppContainer(root)
    app = FastAPI(title="pi5-sdk-orchestrator", version="0.1.0")
    app.state.container = container

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/tasks/{task_id}", response_model=TaskResponse)
    async def get_task(task_id: str) -> TaskResponse:
        task = container.store.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return TaskResponse(
            id=task.id,
            state=task.state,
            retry_count=task.retry_count,
            idempotency_key=task.idempotency_key,
            last_error=task.last_error,
            result_summary=task.result_summary,
        )

    @app.post("/tasks/{task_id}/retry", response_model=TaskResponse)
    async def retry_task(task_id: str) -> TaskResponse:
        try:
            task = container.engine.retry_task(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        return TaskResponse(
            id=task.id,
            state=task.state,
            retry_count=task.retry_count,
            idempotency_key=task.idempotency_key,
            last_error=task.last_error,
            result_summary=task.result_summary,
        )

    @app.post("/webhook/github")
    async def github_webhook(
        request: Request,
        x_github_delivery: str = Header(default=""),
        x_hub_signature_256: str = Header(default=""),
    ) -> dict[str, str | bool]:
        payload_bytes = await request.body()
        _verify_signature(payload_bytes, x_hub_signature_256, os.getenv("GITHUB_WEBHOOK_SECRET", ""))

        payload = await request.json()
        issue = payload.get("issue")
        if not issue:
            raise HTTPException(status_code=400, detail="Unsupported payload")

        labels = {item["name"] for item in issue.get("labels", [])}
        if "agent" not in labels:
            return {"accepted": False, "reason": "missing agent label"}

        try:
            task, created = container.engine.enqueue_from_webhook(payload, x_github_delivery)
        except ValueError as exc:
            return {"accepted": False, "reason": str(exc)}

        if created:
            await container.engine.process_task(task.id)

        return {"accepted": True, "task_id": task.id, "created": created}

    return app


def _verify_signature(payload: bytes, provided_sig: str, secret: str) -> None:
    if not secret:
        return
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, provided_sig):
        raise HTTPException(status_code=401, detail="Invalid signature")


app = create_app()
