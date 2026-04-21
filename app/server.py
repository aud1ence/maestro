from __future__ import annotations

import hashlib
import hmac
import logging
import os
import subprocess
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
        default_env = self.config.github_auth.default_token_env
        issue_env = self.config.github_auth.issue_comment_token_env
        pr_env = self.config.github_auth.pull_request_token_env
        self.github_client = GitHubClient(
            api_base=self.config.github_api_base,
            default_token=os.getenv(default_env),
            issue_comment_token=os.getenv(issue_env),
            pull_request_token=os.getenv(pr_env),
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

    @app.get("/health/readiness")
    async def readiness() -> dict[str, object]:
        claude = _check_claude_auth()
        codex = _check_codex_auth()
        gh = _github_auth_readiness(container.config)
        all_ok = claude["authenticated"] and codex["authenticated"] and gh["issue_comment_token_configured"]
        return {
            "status": "ok" if all_ok else "degraded",
            "cli": {"claude": claude, "codex": codex},
            "github": gh,
        }

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


def _run_auth_status(command: list[str], timeout_seconds: int = 8) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        return 127, "binary not found"
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout_seconds}s"
    output = f"{completed.stdout}\n{completed.stderr}".strip()
    return completed.returncode, output


def _check_claude_auth() -> dict[str, object]:
    rc, output = _run_auth_status(["claude", "auth", "status"])
    is_logged_in = rc == 0 and '"loggedIn": true' in output
    status_summary = "logged_in" if is_logged_in else "not_logged_in"
    return {
        "installed": rc != 127,
        "authenticated": is_logged_in,
        "status": status_summary,
        "check_command": "claude auth status",
        "login_command": "claude auth login",
        "login_hint": "Run login command to get browser/device URL for authentication.",
    }


def _check_codex_auth() -> dict[str, object]:
    rc, output = _run_auth_status(["codex", "login", "status"])
    is_logged_in = rc == 0 and "Logged in" in output
    status_summary = "logged_in" if is_logged_in else "not_logged_in"
    return {
        "installed": rc != 127,
        "authenticated": is_logged_in,
        "status": status_summary,
        "check_command": "codex login status",
        "login_command": "codex login --device-auth",
        "login_hint": "Run login command to get browser/device URL (or use --with-api-key).",
    }


def _github_auth_readiness(config: AppConfig) -> dict[str, object]:
    default_env = config.github_auth.default_token_env
    issue_env = config.github_auth.issue_comment_token_env
    pr_env = config.github_auth.pull_request_token_env
    default_set = bool(os.getenv(default_env))
    issue_set = bool(os.getenv(issue_env))
    pr_set = bool(os.getenv(pr_env))
    return {
        "default_token_env": default_env,
        "issue_comment_token_env": issue_env,
        "pull_request_token_env": pr_env,
        "default_token_configured": default_set,
        "issue_comment_token_configured": issue_set or default_set,
        "pull_request_token_configured": pr_set or default_set,
    }


app = create_app()
