# pi5-sdk-orchestrator

CLI-native orchestrator for Raspberry Pi 5. All AI roles (Planner, Coder, Reviewer, Docs, Memory) delegate to external CLI agents — no LLM agents with system prompts in Python. Role → CLI backend is config, not code.

Pipeline: `GitHub webhook → PLANNING (CLI) → CODING (CLI) → REVIEWING (CLI) → COMPLETED | retry | NEEDS_HUMAN`

## Quick Start

```bash
uv sync
cp .env.example .env
# Set GITHUB_TOKEN, authenticate each CLI, then install the webhook on any GitHub repo
uv run uvicorn app.server:app --host 0.0.0.0 --port 8000
```

## Features

- Role-based CLI routing — each role has its own `backend`, `fallback_backend`, and `flags`
- Policy guard — only binaries listed in `allowed_commands` can be executed
- Review decision parsing — reviewer outputs `APPROVED` / `CHANGES_REQUESTED` / `NEEDS_HUMAN` on the first line
- Retry loop — `CHANGES_REQUESTED` triggers re-plan → re-code → re-review, up to `reviewer_changes_threshold` times
- SQLite task store with idempotency key and state machine
- Multi-repo support — any repo can send a webhook; workspace is isolated per repo at `workspaces/<owner>/<repo>`
- GitHub issue comments via a single PAT (`GITHUB_TOKEN`)
- Repo auto-sync (clone on first run, pull on subsequent runs)
- Wiki context provider interface (null implementation by default)
- CLI auth diagnostics — appends login hint to task stderr when a CLI is not authenticated
- Readiness endpoint — reports auth status for each CLI and GitHub token

## Documentation

- [Architecture](docs/architecture.md) — pipeline diagram, role → CLI mapping, state machine, project structure
- [Configuration](docs/configuration.md) — environment variables, `config/agent.yaml` reference, multi-repo setup, CLI auth
- [API Reference](docs/api.md) — endpoint table and curl examples
- [Deploying on Raspberry Pi 5](docs/deployment-pi5.md) — system setup, CLI install, systemd service, webhook config, troubleshooting

## Tests

```bash
uv run pytest -q                                          # full suite
uv run pytest -q tests/test_orchestrator_integration.py  # integration only
uv run pytest -q -k "test_happy_path_to_completed"       # single test
```

## Notes

- The coder delegates entirely to the CLI — no code-writing logic exists in Python
- The retry loop re-runs the full pipeline (re-plan + re-code + re-review) without carrying over state from the previous attempt
- `docs` and `memory` roles are configured but not yet wired into the pipeline (extension points)
- GitHub comments are silently skipped when `GITHUB_TOKEN` is not set
