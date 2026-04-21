from __future__ import annotations

import subprocess
from pathlib import Path


class RepoWorkspaceManager:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def ensure_synced(self, full_name: str, clone_url: str | None = None) -> Path:
        """Clone or pull a repo. Path is derived as <root>/<owner>/<repo>."""
        workspace = (self.root / full_name).resolve()
        workspace.parent.mkdir(parents=True, exist_ok=True)
        actual_clone_url = clone_url or f"https://github.com/{full_name}.git"

        if (workspace / ".git").exists():
            self._run(["git", "fetch", "--all", "--prune"], workspace)
            self._run(["git", "pull", "--ff-only"], workspace)
            return workspace

        self._run(["git", "clone", actual_clone_url, str(workspace)], workspace.parent)
        return workspace

    def _run(self, cmd: list[str], cwd: Path) -> None:
        completed = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(f"Command failed: {' '.join(cmd)} | {detail}")
