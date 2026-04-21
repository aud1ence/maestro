from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from app.schemas import ExecutionConfig


class OrchestratorConfig(BaseModel):
    max_retries: int = 2
    reviewer_changes_threshold: int = 1


class PolicyConfig(BaseModel):
    allowed_commands: list[str] = Field(default_factory=lambda: ["claude", "codex", "git", "pytest", "uv"])
    allowed_paths: list[str] = Field(default_factory=list)
    branch_prefix: str = "agent/"


class PromptConfig(BaseModel):
    planner_system: str = "You are a planner agent. Return concise, actionable plans."
    reviewer_system: str = "You are a reviewer agent. Focus on correctness and safety."


class RepoConfig(BaseModel):
    target_full_name: str = "aud1ence/obsidian-wiki-mcp"
    clone_url: str = "https://github.com/aud1ence/obsidian-wiki-mcp.git"
    local_path: str = "workspaces/obsidian-wiki-mcp"
    sync_on_task: bool = True


class AppConfig(BaseModel):
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    prompts: PromptConfig = Field(default_factory=PromptConfig)
    repo: RepoConfig = Field(default_factory=RepoConfig)
    github_api_base: str = "https://api.github.com"
    use_openai_sdk: bool = False


DEFAULT_CONFIG_PATH = Path("config/agent.yaml")


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    if not path.exists():
        return AppConfig()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return AppConfig.model_validate(raw)
