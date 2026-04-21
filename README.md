# pi5-sdk-orchestrator

Hybrid orchestrator for Raspberry Pi 5 using OpenAI Agents SDK + CLI coding agents (Claude primary, Codex fallback).

## Features (v1)

- FastAPI webhook API with GitHub signature verification.
- SQLite task store with idempotency key and lifecycle state tracking.
- Orchestrator pipeline: `queued -> planning -> coding -> reviewing -> completed|failed|needs_human`.
- Planner/Reviewer agent facade with optional OpenAI Agents SDK structured output.
- CLI executor adapter with backend fallback and timeout handling.
- CLI auth diagnostics with login hints (`claude auth login`, `codex login --device-auth`) when execution fails due to missing auth.
- Policy guard for command/path/branch restrictions.
- GitHub issue comment + PR client interface with role-based PAT support.
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

Recommended env variables:

```bash
# Optional: OpenAI Agents SDK
OPENAI_API_KEY=

# GitHub PATs (role-based preferred)
GITHUB_ISSUE_TOKEN=
GITHUB_PR_TOKEN=

# Optional fallback token for both roles
GITHUB_TOKEN=

# Optional webhook signature verification
GITHUB_WEBHOOK_SECRET=
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
- `GET /health/readiness` (CLI auth + GitHub token readiness)

Example:

```bash
curl -s http://127.0.0.1:8000/health/readiness
```

`status=ok` requires:
- Claude authenticated
- Codex authenticated
- issue-comment GitHub token configured (`GITHUB_ISSUE_TOKEN` or fallback `GITHUB_TOKEN`)

## Tests

```bash
uv run pytest -q
```

## CLI Authentication

Check status:

```bash
claude auth status
codex login status
```

Login:

```bash
claude auth login
codex login --device-auth
```

When CLI is not authenticated, orchestrator appends an explicit login hint to task stderr for faster operator recovery.

## GitHub Tokens by Role

Configure token env names in `config/agent.yaml` under `github_auth`:

- `default_token_env` (fallback for all GitHub actions)
- `issue_comment_token_env` (used by issue comments)
- `pull_request_token_env` (used by PR creation)

Default mapping:

```yaml
github_auth:
  default_token_env: GITHUB_TOKEN
  issue_comment_token_env: GITHUB_ISSUE_TOKEN
  pull_request_token_env: GITHUB_PR_TOKEN
```

## Notes

- v1 uses local workspace isolation with policy guard, no per-task Docker sandbox yet.
- Requires `claude` and/or `codex` binaries available in runtime environment for live coding execution.
