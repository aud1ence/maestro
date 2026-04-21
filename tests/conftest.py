from __future__ import annotations

from pathlib import Path

import pytest

from app.config import AppConfig, OrchestratorConfig, PolicyConfig, PromptConfig
from app.policy import PolicyGuard
from app.schemas import ExecutionConfig
from app.store import TaskStore
from app.tools.cli_executor import CLIExecutor


@pytest.fixture
def temp_store(tmp_path: Path) -> TaskStore:
    return TaskStore(tmp_path / "tasks.sqlite")


@pytest.fixture
def app_config() -> AppConfig:
    return AppConfig(
        execution=ExecutionConfig(
            backend="claude",
            fallback_backend="codex",
            flags=[],
            verify_commands=[],
            skill="default",
            risk_level="medium",
        ),
        orchestrator=OrchestratorConfig(max_retries=2, reviewer_changes_threshold=1),
        policy=PolicyConfig(
            allowed_commands=["claude", "codex", "kiro-cli", "gemini", "uv", "pytest", "git"],
            allowed_paths=[],
            branch_prefix="agent/",
        ),
        prompts=PromptConfig(),
        use_openai_sdk=False,
    )


@pytest.fixture
def cli_executor(tmp_path: Path, app_config: AppConfig) -> CLIExecutor:
    policy = PolicyGuard(app_config.policy, tmp_path)
    return CLIExecutor(policy, tmp_path)
