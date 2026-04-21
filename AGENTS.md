# Repository Guidelines

## Project Structure & Module Organization
The orchestration service lives in `app/`.
- `app/server.py`: FastAPI entrypoint and route wiring.
- `app/orchestrator.py`: task lifecycle engine.
- `app/store.py`: SQLite persistence (`data/tasks.sqlite`).
- `app/tools/`: integrations (CLI executor, GitHub client, repo sync, wiki context).
- `app/config.py`, `app/policy.py`, `app/schemas.py`: config loading, guardrails, and typed models.

Configuration is in `config/agent.yaml`; environment template is `.env.example`; tests are in `tests/`; runtime workspace clones are under `workspaces/`.

## Build, Test, and Development Commands
- `uv sync`: install runtime + dev dependencies from `pyproject.toml`/`uv.lock`.
- `cp .env.example .env`: create local env file before running webhook flows.
- `uv run uvicorn app.server:app --host 0.0.0.0 --port 8000`: start the API locally.
- `uv run pytest -q`: run full Python test suite.
- `uv run pytest -q tests/test_orchestrator_integration.py`: run a focused integration file.

For the synced target repo (`workspaces/obsidian-wiki-mcp`), use `npm run build|test|lint` only when changing that workspace.

## Coding Style & Naming Conventions
Use Python 3.11+ with 4-space indentation, type hints, and `snake_case` for functions/variables. Keep module-level responsibilities narrow (API, orchestration, storage, tools). Prefer small, typed Pydantic/enum-backed interfaces for cross-module contracts.

In tests, mirror source filenames when possible (for example, `app/store.py` -> `tests/test_store.py`).

## Testing Guidelines
Framework: `pytest` with `pytest-asyncio` for async paths. Add tests for every state transition change (`queued -> ... -> completed|failed|needs_human`) and for policy/security checks.

Keep tests deterministic: stub CLI/agent/GitHub dependencies (see existing stubs in `tests/test_orchestrator_integration.py`).

## Commit & Pull Request Guidelines
This repository currently has no commit history on `master`, so adopt Conventional Commits now (for example, `feat: add retry guard for failed tasks`, `fix: validate webhook signature`).

PRs should include:
- clear behavior summary and affected modules,
- linked issue/task,
- test evidence (`uv run pytest -q` output),
- API example payload/response when endpoint behavior changes.

## Security & Configuration Tips
Do not commit secrets; keep tokens/webhook secrets in `.env`. Enforce command/path restrictions via `config/agent.yaml` policy settings, and keep allowed target repos explicit.
