# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 0. Language

All code, comments, docstrings, variable names, log messages, error strings, and config file comments must be in **English**. Vietnamese is used only in conversation with the user — never in any file committed to the repository.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing anything in this codebase:
- State assumptions explicitly — e.g. "I'm assuming this CLI follows the `-p <prompt>` convention"
- When a task touches the pipeline (orchestrator → agents → CLI), present tradeoffs before proceeding — changes here affect retry logic and state machine
- If the task is ambiguous about _which_ CLI role to modify vs. the pipeline logic, stop and ask
- Push back when a simpler approach exists — e.g. a YAML config change instead of new Python code

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- Role → CLI mapping is config, not code. Prefer a YAML change over a new class.
- No abstractions for single-use CLI backends — `_build_command()` handles special cases with `if` statements, not a registry.
- No error handling for scenarios that `PolicyGuard` already prevents.
- The retry loop is intentionally simple (recursive `process_task()`). Don't replace it with a framework unless the complexity justifies it.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

This codebase has clear module boundaries — respect them:
- Changes to `config.py` (new fields) must not touch `orchestrator.py` unless the pipeline actually uses the field.
- Changes to the state machine (`store.py:STATE_TRANSITIONS`) must not change `orchestrator.py` logic unless the transition is part of the same task.
- Match existing style — `async/await`, Pydantic models for cross-module contracts, dataclasses for internal records.
- If you spot unrelated dead code (e.g. `use_openai_sdk` flag), mention it — don't delete it.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

For tasks in this repo, frame success as:

| Task type | Success criteria |
|-----------|-----------------|
| Add new CLI role | `uv run pytest -q` passes + role config loads from YAML + `PolicyGuard` allows the binary |
| Change pipeline logic | State transitions in `test_orchestrator_integration.py` assert the new final state |
| Add new state | `STATE_TRANSITIONS` updated + at least one test exercises the new transition |
| Change review decision parsing | Direct unit test on `_parse_decision()` with the new keyword |

For multi-step changes, state a plan first:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
```

Run `uv run pytest -q` after each logical step.

---

## Commands

```bash
uv sync                          # install dependencies
uv run pytest -q                 # full test suite
uv run pytest -q tests/test_orchestrator_integration.py  # integration only
uv run pytest -q -k "test_happy_path_to_completed"       # single test
uv run uvicorn app.server:app --host 0.0.0.0 --port 8000  # start server
```

## Architecture

All AI intelligence is delegated to CLI agents — there are no LLM agents with system prompts in Python. `AgentsFacade` is a CLI caller, not an agent runner.

**Pipeline flow** (driven by `OrchestratorEngine.process_task()`):

```
GitHub webhook → PLANNING (planner CLI) → CODING (coder CLI) → REVIEWING (reviewer CLI)
                                                                      │
                         CHANGES_REQUESTED + retry < threshold ───────┘ (loops back to PLANNING)
                         CHANGES_REQUESTED + retry ≥ threshold ──────→ NEEDS_HUMAN
                         APPROVED ───────────────────────────────────→ COMPLETED
```

**Role → CLI mapping** lives entirely in `config/agent.yaml` under `roles:`. Each role has `backend`, `fallback_backend`, and `flags`. Switching a role's CLI requires only a YAML change. Any binary following `<name> -p <prompt>` works automatically; `codex` is the only exception using `codex exec <prompt>` (see `CLIExecutor._build_command()`).

**Review decision protocol**: `AgentsFacade.review()` prompts the reviewer CLI to output `APPROVED`, `CHANGES_REQUESTED`, or `NEEDS_HUMAN` on the first line. `_parse_decision()` searches for keywords in that priority order, defaulting to `APPROVED`.

**State machine** is enforced by `TaskStore.transition_state()` against `STATE_TRANSITIONS` in `app/store.py`. `CODING → PLANNING` is explicitly allowed for retry loops. Adding a new state requires updating that dict.

**PolicyGuard** (`app/policy.py`) validates every subprocess command against `allowed_commands` in config before execution. When adding a new CLI backend, add it to `policy.allowed_commands` in `config/agent.yaml`.

## Key Wiring

`AppContainer` in `app/server.py` wires all dependencies. `AgentsFacade` requires a `CLIExecutor` instance — it is created as `AgentsFacade(config, cli_executor)`.

`OrchestratorEngine` accepts a `wiki_context: WikiContextProvider` (optional). The null implementation is used by default; inject a real implementation to provide Obsidian Wiki context to the planner prompt.

## Test Stubs

Integration tests in `tests/test_orchestrator_integration.py` use `StubAgents` (implements `plan()` and `review()`) and `StubCLI` (implements `execute()`) to avoid real subprocess calls. When adding pipeline logic, stub at these interfaces.
