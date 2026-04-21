from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from app.policy import PolicyGuard, PolicyViolationError


@dataclass
class CLIResult:
    backend: str
    returncode: int
    stdout: str
    stderr: str
    command: list[str]

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class CLIExecutor:
    def __init__(self, policy_guard: PolicyGuard, workspace: Path):
        self.policy_guard = policy_guard
        self.workspace = workspace.resolve()

    async def execute(
        self,
        *,
        prompt: str,
        backend: str,
        fallback_backend: str | None,
        flags: list[str],
        timeout_seconds: int = 900,
        workspace: Path | None = None,
    ) -> CLIResult:
        target_workspace = (workspace or self.workspace).resolve()
        primary_cmd = self._build_command(backend, prompt, flags)
        primary = await self._run_command(primary_cmd, timeout_seconds, target_workspace)
        if primary.ok or not fallback_backend:
            return primary

        fallback_cmd = self._build_command(fallback_backend, prompt, flags)
        fallback = await self._run_command(fallback_cmd, timeout_seconds, target_workspace)
        return fallback

    async def run_shell_command(self, command: str, timeout_seconds: int = 300) -> CLIResult:
        cmd = ["uv", "run", "bash", "-lc", command]
        return await self._run_command(cmd, timeout_seconds, self.workspace)

    def _build_command(self, backend: str, prompt: str, flags: list[str]) -> list[str]:
        if backend == "claude":
            return ["claude", "-p", prompt, *flags]
        if backend == "codex":
            return ["codex", "exec", prompt, *flags]
        raise PolicyViolationError(f"Unsupported backend: {backend}")

    async def _run_command(self, command: list[str], timeout_seconds: int, workspace: Path) -> CLIResult:
        self.policy_guard.validate_command(command)
        self.policy_guard.validate_path(workspace)

        proc = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout_seconds)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return CLIResult(
                backend=command[0],
                returncode=124,
                stdout="",
                stderr=f"Command timed out after {timeout_seconds}s",
                command=command,
            )

        return CLIResult(
            backend=command[0],
            returncode=proc.returncode or 0,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
            command=command,
        )
