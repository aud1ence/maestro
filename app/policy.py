from __future__ import annotations

from pathlib import Path

from app.config import PolicyConfig


class PolicyViolationError(RuntimeError):
    pass


class PolicyGuard:
    def __init__(self, config: PolicyConfig, workspace_root: Path):
        self.config = config
        self.workspace_root = workspace_root.resolve()

    def validate_command(self, command: list[str]) -> None:
        if not command:
            raise PolicyViolationError("Empty command is not allowed")
        executable = command[0]
        if executable not in self.config.allowed_commands:
            raise PolicyViolationError(f"Command not allowed: {executable}")

    def validate_path(self, target: Path) -> None:
        resolved = target.resolve()
        if not str(resolved).startswith(str(self.workspace_root)):
            raise PolicyViolationError(f"Path outside workspace: {resolved}")

    def validate_branch_name(self, branch: str) -> None:
        if not branch.startswith(self.config.branch_prefix):
            raise PolicyViolationError(
                f"Branch must start with {self.config.branch_prefix}, got {branch}"
            )
