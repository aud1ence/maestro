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

## Kiến trúc tổng quan

Tất cả AI intelligence delegate cho CLI agents — không có LLM agents với system prompts trong Python code. `app/agents.py` chỉ là CLI caller, không phải agent runner.

```
AgentsFacade.plan()   → config.roles.planner.backend -p "<prompt>"
AgentsFacade.review() → config.roles.reviewer.backend -p "<prompt>"  (parse APPROVED/CHANGES_REQUESTED/NEEDS_HUMAN)
CLIExecutor.execute() → config.roles.coder.backend   -p "<prompt>"   (called directly from orchestrator)
```

Role → CLI backend mapping sống trong `config/agent.yaml`. Thêm/đổi CLI: chỉ sửa YAML.

## Project Structure

- `app/server.py`: FastAPI entrypoint, AppContainer wiring.
- `app/orchestrator.py`: Task lifecycle engine — state machine, retry loop, GitHub comment.
- `app/agents.py`: `AgentsFacade` — gọi planner CLI và reviewer CLI, parse review decision.
- `app/store.py`: SQLite task store (`data/tasks.sqlite`), state machine guard.
- `app/config.py`: `AppConfig` với `RolesConfig` (per-role backend/flags), `PolicyConfig`.
- `app/policy.py`: `PolicyGuard` — validate command/path trước khi chạy subprocess.
- `app/tools/cli_executor.py`: Subprocess runner, fallback backend, timeout, auth hints.
- `app/tools/github_client.py`: GitHub issue comment + PR với role-based PAT.
- `app/tools/repo_workspace.py`: clone/pull workspace manager.
- `app/tools/wiki_context.py`: `WikiContextProvider` interface (null impl mặc định).

Config: `config/agent.yaml` — env template: `.env.example` — tests: `tests/` — workspaces: `workspaces/`.

## Build, Test, Dev Commands

```bash
uv sync                                                               # install dependencies
cp .env.example .env                                                  # setup env lần đầu
uv run uvicorn app.server:app --host 0.0.0.0 --port 8000             # start API
uv run pytest -q                                                      # full test suite
uv run pytest -q tests/test_orchestrator_integration.py              # focused
uv run pytest -q -k "test_happy_path_to_completed"                   # single test
```

Target workspace (`workspaces/obsidian-wiki-mcp`): dùng `npm run build|test|lint` chỉ khi thay đổi workspace đó.

## CLI Command Convention

Binary không phải `codex` → dùng `[backend, "-p", prompt, *flags]`.  
Binary `codex` → dùng `["codex", "exec", prompt, *flags]`.

Khi thêm CLI backend mới với syntax khác, update `CLIExecutor._build_command()`.

## Review Decision Protocol

`AgentsFacade.review()` gọi reviewer CLI với prompt yêu cầu output keyword trên dòng đầu:
- `APPROVED` → pipeline tiếp tục → COMPLETED
- `CHANGES_REQUESTED` → retry (re-plan + re-code + re-review) nếu chưa quá threshold
- `NEEDS_HUMAN` → dừng, escalate

`_parse_decision(text)` tìm keyword theo thứ tự `CHANGES_REQUESTED` → `NEEDS_HUMAN` → `APPROVED` (default).

## State Machine

```
QUEUED → PLANNING → CODING → REVIEWING → COMPLETED
                   ↑          ↓              (terminal)
                   └──────────┘ (CHANGES_REQUESTED retry)
                              ↓
                        NEEDS_HUMAN  (terminal, có thể → QUEUED qua retry endpoint)
                        FAILED       (terminal)
```

Transition guards sống trong `app/store.py:STATE_TRANSITIONS`. `CODING → PLANNING` được phép (retry). Khi thêm state mới: update dict này.

## Testing Guidelines

Framework: `pytest` với `pytest-asyncio`. Stub CLI/agent/GitHub trong integration tests (không call real subprocess).

Test mỗi state transition quan trọng. Khi thêm role mới hoặc sửa pipeline logic: thêm test case trong `test_orchestrator_integration.py` với `StubAgents` + `StubCLI` tương ứng.

`StubAgents` phải implement `plan()` và `review()` — đây là contract của `AgentsFacade`.

## Security

- Không commit secrets — tokens/webhook secret chỉ trong `.env`
- `PolicyGuard.validate_command()` chạy trước mọi subprocess — `allowed_commands` trong YAML
- Target repo hardcoded trong `config.repo.target_full_name` — không chạy CLI trên repo tùy ý
- HMAC signature verify cho GitHub webhook (khi `GITHUB_WEBHOOK_SECRET` được set)

## Commit & PR Guidelines

Conventional Commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`.

PR cần:
- Mô tả behavior thay đổi và module bị ảnh hưởng
- Test evidence (`uv run pytest -q` output)
- API example nếu endpoint thay đổi
