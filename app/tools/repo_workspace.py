from __future__ import annotations

import subprocess
from pathlib import Path


class RepoWorkspaceManager:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def ensure_synced(self, clone_url: str, local_relative_path: str) -> Path:
        workspace = (self.root / local_relative_path).resolve()
        workspace.parent.mkdir(parents=True, exist_ok=True)

        if (workspace / ".git").exists():
            self._run(["git", "fetch", "--all", "--prune"], workspace)
            self._run(["git", "pull", "--ff-only"], workspace)
            return workspace

        self._run(["git", "clone", clone_url, str(workspace)], self.root)
        return workspace

    def _run(self, cmd: list[str], cwd: Path) -> None:
        completed = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(f"Command failed: {' '.join(cmd)} | {detail}")
