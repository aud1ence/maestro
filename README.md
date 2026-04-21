# pi5-sdk-orchestrator

CLI-native orchestrator for Raspberry Pi 5. All AI roles (Planner, Coder, Reviewer, Docs, Memory) delegate to external CLI agents — no LLM agents with system prompts in Python. Role → CLI backend is config, not code.

Pipeline: `GitHub webhook → PLANNING (CLI) → CODING (CLI) → REVIEWING (CLI) → COMPLETED | retry | NEEDS_HUMAN`

## Architecture

```
GitHub Issue (label "agent")
         │
         ▼
POST /webhook/github  (FastAPI, HMAC signature verify)
         │
         ▼
OrchestratorEngine
  ├── PLANNING  → AgentsFacade.plan()   → config.roles.planner.backend -p "..."
  ├── CODING    → CLIExecutor.execute() → config.roles.coder.backend   -p "..."
  └── REVIEWING → AgentsFacade.review() → config.roles.reviewer.backend -p "..."
         │
         ├─ APPROVED                          → COMPLETED + GitHub comment
         ├─ CHANGES_REQUESTED (retry < limit) → loop back to PLANNING
         ├─ CHANGES_REQUESTED (retry ≥ limit) → NEEDS_HUMAN
         └─ NEEDS_HUMAN                       → NEEDS_HUMAN + GitHub comment
```

## Role → CLI Mapping

Configured in `config/agent.yaml`. Switch any role's CLI by editing one line — no code changes needed.

```yaml
roles:
  planner:
    backend: kiro-cli # kiro-cli -p "decompose issue..."
    fallback_backend: claude
  coder:
    backend: claude # claude -p "..." --allowedTools Bash,Read,Write,Edit
    fallback_backend: codex
    flags: ["--allowedTools", "Bash,Read,Write,Edit"]
  reviewer:
    backend: codex # codex exec "review... APPROVED|CHANGES_REQUESTED|NEEDS_HUMAN"
  docs:
    backend: gemini # optional — not yet wired into pipeline
  memory:
    backend: kiro-cli # optional — not yet wired into pipeline
```

Any binary following `<name> -p <prompt>` works without code changes. `codex` is the only exception — it uses `codex exec <prompt>` (handled in `CLIExecutor._build_command()`).

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

## Quick Start

```bash
uv sync
cp .env.example .env
# Set GITHUB_TOKEN, authenticate each CLI (see CLI Auth below), then
# install the webhook on any GitHub repo you want the agent to handle
uv run uvicorn app.server:app --host 0.0.0.0 --port 8000
```

## Multi-repo Support

Any GitHub repository can trigger the agent — there is no hardcoded repo allowlist. Access control is via the HMAC webhook secret (`GITHUB_WEBHOOK_SECRET`). **Set this in production.**

When a webhook arrives, the orchestrator:
1. Verifies the HMAC signature (if `GITHUB_WEBHOOK_SECRET` is set)
2. Checks that the issue has the `agent` label
3. Clones or pulls the repo into `workspaces/<owner>/<repo>` (derived from `repository.full_name`)
4. Runs the full pipeline in that workspace

To add a new repo: install the webhook on that repo pointing to `POST /webhook/github`.

## Environment Variables

```bash
# GitHub personal access token — repo scope covers issue comments and PR creation
GITHUB_TOKEN=

# Webhook HMAC secret — set in GitHub repo settings → Webhooks (optional, skipped if empty)
GITHUB_WEBHOOK_SECRET=

# CLI tools authenticate via their own OAuth/device auth flows — see CLI Auth below
# Optional: use API key instead of device auth for codex
OPENAI_API_KEY=
```

## API

| Method | Path                | Description                            |
| ------ | ------------------- | -------------------------------------- |
| `POST` | `/webhook/github`   | Receive GitHub Issue webhook           |
| `GET`  | `/tasks/{id}`       | Get task state and result              |
| `POST` | `/tasks/{id}/retry` | Reset a `needs_human` task to `queued` |
| `GET`  | `/health`           | Liveness check                         |
| `GET`  | `/health/readiness` | CLI auth status + GitHub token check   |

```bash
# Check readiness
curl -s http://localhost:8000/health/readiness | python3 -m json.tool

# Send a test webhook
curl -X POST http://localhost:8000/webhook/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Delivery: test-001" \
  -d '{
    "action": "labeled",
    "issue": {"id": 1, "number": 1, "title": "Fix bug", "body": "Details...", "labels": [{"name": "agent"}]},
    "repository": {"full_name": "owner/repo"},
    "sender": {"login": "user"}
  }'
```

## Project Structure

```
app/
├── server.py             # FastAPI endpoints + AppContainer wiring
├── orchestrator.py       # Pipeline engine (planning → coding → reviewing → outcome)
├── agents.py             # AgentsFacade — CLI caller for plan() and review()
├── config.py             # AppConfig, RolesConfig (per-role backend/flags)
├── policy.py             # PolicyGuard — command and path allowlist
├── schemas.py            # TaskState, PipelineDecision, ExecutionConfig
├── store.py              # SQLite TaskStore + state machine
└── tools/
    ├── cli_executor.py   # Subprocess runner with timeout, fallback, auth hints
    ├── github_client.py  # GitHub API (issue comment, PR creation)
    ├── repo_workspace.py # clone/pull workspace manager
    └── wiki_context.py   # WikiContextProvider interface (null impl by default)
config/agent.yaml         # Roles, policy, repo, prompts, orchestrator settings
data/tasks.sqlite         # Task persistence (auto-created)
workspaces/               # Cloned repos, isolated per repo at workspaces/<owner>/<repo>
```

## Configuration (`config/agent.yaml`)

```yaml
roles:
  planner:
    backend: claude
    fallback_backend: null
    flags: []
  coder:
    backend: claude
    fallback_backend: codex
    flags: ["--allowedTools", "Bash,Read,Write,Edit"]
  reviewer:
    backend: codex
    flags: []

orchestrator:
  max_retries: 2
  reviewer_changes_threshold: 1 # CHANGES_REQUESTED retries before escalating to needs_human

policy:
  allowed_commands: [claude, codex, kiro-cli, gemini, git, uv, pytest]
  branch_prefix: "agent/"

repo:
  sync_on_task: true  # workspace is auto-derived as workspaces/<owner>/<repo>

execution:
  verify_commands:
    - "uv run pytest -q" # runs after coding; non-zero exit feeds into reviewer as failure context
```

## Review Decision Protocol

The reviewer CLI is prompted to output one of three keywords on the first line:

```
APPROVED
Task completed correctly. README section added as requested.
```

```
CHANGES_REQUESTED
Output does not match the requested format.
```

`_parse_decision()` searches for keywords in priority order: `CHANGES_REQUESTED` → `NEEDS_HUMAN` → `APPROVED` (default).

## Tests

```bash
uv run pytest -q                                          # full suite (18 tests)
uv run pytest -q tests/test_orchestrator_integration.py  # integration only
uv run pytest -q -k "test_happy_path_to_completed"       # single test
```

## CLI Auth

Each CLI manages its own authentication. The `/health/readiness` endpoint reports current auth status.

```bash
# Claude
claude auth status
claude auth login

# Codex
codex login status
codex login --device-auth       # or: codex login --with-api-key

# Kiro
kiro-cli auth login

# Gemini
gemini auth login
```

When a CLI is not authenticated, the orchestrator appends the relevant login command to the task's `last_error` field so the operator knows what action to take.

## Notes

- The coder delegates entirely to the CLI — no code-writing logic exists in Python
- The retry loop re-runs the full pipeline (re-plan + re-code + re-review) without carrying over state from the previous attempt
- `docs` and `memory` roles are configured but not yet wired into the pipeline (extension points)
- GitHub comments are silently skipped when `GITHUB_TOKEN` is not set
