# pi5-sdk-orchestrator

Hybrid orchestrator for Raspberry Pi 5 using OpenAI Agents SDK + CLI coding agents (Claude primary, Codex fallback).

## Features (v1)

- FastAPI webhook API with GitHub signature verification.
- SQLite task store with idempotency key and lifecycle state tracking.
- Orchestrator pipeline: `queued -> planning -> coding -> reviewing -> completed|failed|needs_human`.
- Planner/Reviewer agent facade with optional OpenAI Agents SDK structured output.
- CLI executor adapter with backend fallback and timeout handling.
- Policy guard for command/path/branch restrictions.
- GitHub issue comment + PR client interface.
- Target repo locking + auto sync (clone/pull) for `aud1ence/obsidian-wiki-mcp`.
- Config-driven behavior via `config/agent.yaml`.
- Pytest suite for unit/integration coverage of core flows.

## Project Layout

- `app/server.py`: API endpoints and app wiring.
- `app/orchestrator.py`: core pipeline engine.
- `app/agents.py`: planner/reviewer SDK facade.
- `app/store.py`: SQLite persistence and state guard.
- `app/policy.py`: guardrail checks.
- `app/tools/cli_executor.py`: CLI execution and fallback.
- `app/tools/github_client.py`: GitHub integration client.
- `app/tools/repo_workspace.py`: clone/pull workspace manager.
- `app/tools/wiki_context.py`: context provider interface.
- `config/agent.yaml`: execution/policy/repo/prompt config.

## Quick Start

```bash
uv sync
cp .env.example .env
uv run uvicorn app.server:app --host 0.0.0.0 --port 8000
```

## Target Repo Connection

Default config is pre-wired to:

- `target_full_name`: `aud1ence/obsidian-wiki-mcp`
- `clone_url`: `https://github.com/aud1ence/obsidian-wiki-mcp.git`
- `local_path`: `workspaces/obsidian-wiki-mcp`

On each accepted task, orchestrator syncs this repo (clone first time, then pull).

## API

- `POST /webhook/github`
- `POST /tasks/{task_id}/retry`
- `GET /tasks/{task_id}`
- `GET /health`

## Tests

```bash
uv run pytest -q
```

## Notes

- v1 uses local workspace isolation with policy guard, no per-task Docker sandbox yet.
- Requires `claude` and/or `codex` binaries available in runtime environment for live coding execution.
