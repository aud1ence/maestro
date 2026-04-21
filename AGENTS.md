# Repository Guidelines

## Language

All code, comments, docstrings, log messages, error strings, and config file comments must be written in **English**. This applies to every file in the repository — Python, YAML, shell scripts, and plain-text configs alike.

## Behavioral Principles (Karpathy-Inspired)

### Think Before Coding

Before implementing: state assumptions, surface ambiguity, present tradeoffs. In this codebase specifically — if a task _could_ be solved by a YAML change vs. new Python code, say so and let the user decide.

If a change touches the pipeline flow (orchestrator → agents → CLI), explain the impact on retry behavior and state transitions before proceeding.

### Simplicity First

The codebase is intentionally thin. Resist adding abstractions:
- Role routing is config (`RolesConfig`), not a class hierarchy
- The retry loop is a recursive call, not a framework
- `_build_command()` uses `if` statements, not a registry pattern

If a new feature can be expressed as a YAML field + a one-line check in existing code, prefer that over a new module.

### Surgical Changes

Module boundaries are narrow by design. Respect them:
- `app/agents.py` → CLI callers only, no orchestration logic
- `app/orchestrator.py` → pipeline flow only, no GitHub API details
- `app/store.py` → persistence + state machine only

Don't improve adjacent code unless it's part of the task. Match existing style (type hints, Pydantic models for cross-module contracts, dataclasses for internal records).

### Goal-Driven Execution

For every change, state the success criteria before starting:
- New role: YAML loads + policy allows + test stubs match new contract
- Pipeline change: `test_orchestrator_integration.py` asserts the new final state
- New state: `STATE_TRANSITIONS` updated + test exercises the transition

Run `uv run pytest -q` as the verification step after each logical change.

---

## Architecture

All AI intelligence is delegated to CLI agents — no LLM agents with system prompts in Python. `app/agents.py` is a CLI caller, not an agent runner.

```
AgentsFacade.plan()   → config.roles.planner.backend  -p "<prompt>"
AgentsFacade.review() → config.roles.reviewer.backend -p "<prompt>"  (parse APPROVED/CHANGES_REQUESTED/NEEDS_HUMAN)
CLIExecutor.execute() → config.roles.coder.backend    -p "<prompt>"  (called directly from orchestrator)
```

Role → CLI backend mapping lives in `config/agent.yaml`. To add or switch a CLI: edit YAML only.

## Project Structure

- `app/server.py`: FastAPI entrypoint, AppContainer wiring.
- `app/orchestrator.py`: Task lifecycle engine — state machine, retry loop, GitHub comment.
- `app/agents.py`: `AgentsFacade` — calls planner CLI and reviewer CLI, parses review decision.
- `app/store.py`: SQLite task store (`data/tasks.sqlite`), state machine guard.
- `app/config.py`: `AppConfig` with `RolesConfig` (per-role backend/flags), `PolicyConfig`.
- `app/policy.py`: `PolicyGuard` — validates command/path before running subprocess.
- `app/tools/cli_executor.py`: Subprocess runner, fallback backend, timeout, auth hints.
- `app/tools/github_client.py`: GitHub issue comment + PR creation via single PAT.
- `app/tools/repo_workspace.py`: clone/pull workspace manager; path derived as `workspaces/<owner>/<repo>`.
- `app/tools/wiki_context.py`: `WikiContextProvider` interface (null impl by default).

Config: `config/agent.yaml` — env template: `.env.example` — tests: `tests/` — workspaces: `workspaces/`.

## Build, Test, Dev Commands

```bash
uv sync                                                               # install dependencies
cp .env.example .env                                                  # first-time env setup
uv run uvicorn app.server:app --host 0.0.0.0 --port 8000             # start API
uv run pytest -q                                                      # full test suite
uv run pytest -q tests/test_orchestrator_integration.py              # integration only
uv run pytest -q -k "test_happy_path_to_completed"                   # single test
```

## CLI Command Convention

Non-`codex` binaries → `[backend, "-p", prompt, *flags]`.
`codex` → `["codex", "exec", prompt, *flags]`.

When adding a new CLI backend with a different syntax, add a case to `CLIExecutor._build_command()`.

## Review Decision Protocol

`AgentsFacade.review()` calls the reviewer CLI with a prompt that requests a keyword on the first line:
- `APPROVED` → pipeline continues → COMPLETED
- `CHANGES_REQUESTED` → retry (re-plan + re-code + re-review) if under threshold
- `NEEDS_HUMAN` → stop, escalate

`_parse_decision(text)` searches for keywords in order: `CHANGES_REQUESTED` → `NEEDS_HUMAN` → `APPROVED` (default).

## State Machine

```
QUEUED → PLANNING → CODING → REVIEWING → COMPLETED
                   ↑          ↓              (terminal)
                   └──────────┘ (CHANGES_REQUESTED retry)
                              ↓
                        NEEDS_HUMAN  (terminal, can return to QUEUED via retry endpoint)
                        FAILED       (terminal)
```

Transition guards live in `app/store.py:STATE_TRANSITIONS`. `CODING → PLANNING` is explicitly allowed for retry. When adding a new state, update that dict.

## Testing Guidelines

Framework: `pytest` with `pytest-asyncio`. Stub CLI/agent/GitHub in integration tests — no real subprocess calls.

Test every important state transition. When adding a new role or changing pipeline logic, add a test case in `test_orchestrator_integration.py` with the appropriate `StubAgents` + `StubCLI`.

`StubAgents` must implement `plan()` and `review()` — these are the `AgentsFacade` contract.

## Security

- Never commit secrets — tokens and webhook secret belong in `.env` only
- `PolicyGuard.validate_command()` runs before every subprocess — `allowed_commands` is the allowlist in YAML
- Any repo can trigger the agent — `GITHUB_WEBHOOK_SECRET` is the only access control; always set it in production
- HMAC signature verification runs on every webhook when `GITHUB_WEBHOOK_SECRET` is set

## Commit & PR Guidelines

Conventional Commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`.

PRs must include:
- Description of behavior change and affected modules
- Test evidence (`uv run pytest -q` output)
- API example if an endpoint changed
