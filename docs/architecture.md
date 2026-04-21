# Architecture

## Pipeline

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

All AI intelligence is delegated to CLI agents — there are no LLM agents with system prompts in Python. `AgentsFacade` is a CLI caller, not an agent runner.

## Role → CLI Mapping

Role → CLI backend is configured entirely in `config/agent.yaml` under `roles:`. Switching a role's CLI requires only a YAML change — no code changes.

```yaml
roles:
  planner:
    backend: kiro-cli   # kiro-cli -p "decompose issue..."
    fallback_backend: claude
  coder:
    backend: claude     # claude -p "..." --allowedTools Bash,Read,Write,Edit
    fallback_backend: codex
    flags: ["--allowedTools", "Bash,Read,Write,Edit"]
  reviewer:
    backend: codex      # codex exec "review... APPROVED|CHANGES_REQUESTED|NEEDS_HUMAN"
  docs:
    backend: gemini     # optional — not yet wired into pipeline
  memory:
    backend: kiro-cli   # optional — not yet wired into pipeline
```

Any binary following `<name> -p <prompt>` works without code changes. `codex` is the only exception — it uses `codex exec <prompt>` (handled in `CLIExecutor._build_command()`).

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

## Key Wiring

`AppContainer` in `app/server.py` wires all dependencies. `AgentsFacade` requires a `CLIExecutor` instance — it is created as `AgentsFacade(config, cli_executor)`.

`OrchestratorEngine` accepts a `wiki_context: WikiContextProvider` (optional). The null implementation is used by default; inject a real implementation to provide Obsidian Wiki context to the planner prompt.

## PolicyGuard

`app/policy.py` validates every subprocess command against `allowed_commands` in config before execution. When adding a new CLI backend, add it to `policy.allowed_commands` in `config/agent.yaml`.

## State Machine

State transitions are enforced by `TaskStore.transition_state()` against `STATE_TRANSITIONS` in `app/store.py`. `CODING → PLANNING` is explicitly allowed for retry loops. Adding a new state requires updating that dict.
