# pi5-sdk-orchestrator

Hybrid orchestrator cho Raspberry Pi 5: **tất cả roles (Planner, Coder, Reviewer, Docs, Memory) đều delegate sang CLI agents** (claude, codex, kiro-cli, gemini). Role → CLI backend được config trong YAML, switch không cần sửa code.

Pipeline: `GitHub webhook → planning (CLI) → coding (CLI) → reviewing (CLI) → completed | retry | needs_human`

## Kiến trúc

```
GitHub Issue (label "agent")
         │
         ▼
POST /webhook/github  (FastAPI, HMAC signature verify)
         │
         ▼
OrchestratorEngine
  ├── PLANNING  → AgentsFacade.plan()  → config.roles.planner.backend -p "..."
  ├── CODING    → CLIExecutor.execute() → config.roles.coder.backend   -p "..."
  └── REVIEWING → AgentsFacade.review() → config.roles.reviewer.backend -p "..."
         │
         ├─ APPROVED      → TaskState.COMPLETED + GitHub comment
         ├─ CHANGES_REQUESTED (retry < threshold) → re-run từ PLANNING
         └─ CHANGES_REQUESTED (retry ≥ threshold) → TaskState.NEEDS_HUMAN
```

## Role → CLI mapping (config/agent.yaml)

```yaml
roles:
  planner:
    backend: kiro-cli      # kiro-cli -p "decompose issue..."
    fallback_backend: claude
  coder:
    backend: claude        # claude -p "..." --allowedTools Bash,Read,Write,Edit
    fallback_backend: codex
  reviewer:
    backend: codex         # codex exec "review result... Output: APPROVED|CHANGES_REQUESTED|NEEDS_HUMAN"
  docs:
    backend: gemini        # optional
  memory:
    backend: kiro-cli      # optional
```

Thêm CLI mới: bất kỳ binary nào theo convention `<name> -p <prompt>` hoạt động ngay — không cần code thêm. `codex` là exception duy nhất dùng `codex exec <prompt>`.

## Features

- Role-based CLI routing — mỗi role có backend riêng, switch bằng YAML
- Policy guard — chỉ các binary trong `allowed_commands` được phép chạy
- Review decision parsing — reviewer CLI output `APPROVED` / `CHANGES_REQUESTED` / `NEEDS_HUMAN` trên dòng đầu
- Retry loop — `CHANGES_REQUESTED` → re-plan → re-code → re-review, tối đa `reviewer_changes_threshold` lần
- SQLite task store với idempotency key và state machine (`queued → planning → coding → reviewing → completed|failed|needs_human`)
- GitHub issue comment + role-based PAT (issue comment token / PR token tách biệt)
- Repo auto-sync (clone lần đầu, pull những lần sau)
- Wiki context provider interface
- CLI auth diagnostics — gợi ý login command khi CLI chưa auth
- Readiness endpoint — check auth status từng CLI + GitHub token

## Quick Start

```bash
uv sync
cp .env.example .env
# Điền GITHUB_ISSUE_TOKEN, sau đó đăng nhập CLI (xem CLI Auth Check bên dưới)
uv run uvicorn app.server:app --host 0.0.0.0 --port 8000
```

## Environment Variables

```bash
# One PAT with repo scope covers both issue comments and PR creation
GITHUB_TOKEN=

# Webhook HMAC secret (optional — skipped if empty)
GITHUB_WEBHOOK_SECRET=

# CLI tools use their own auth (OAuth/device auth) — see CLI Auth Check below
# Optional: use API key instead of device auth for codex
OPENAI_API_KEY=
```

## API

| Method | Path | Mô tả |
|--------|------|-------|
| `POST` | `/webhook/github` | Nhận GitHub Issue webhook |
| `GET`  | `/tasks/{id}` | Xem trạng thái task |
| `POST` | `/tasks/{id}/retry` | Retry task ở needs_human |
| `GET`  | `/health` | Liveness check |
| `GET`  | `/health/readiness` | CLI auth + GitHub token readiness |

```bash
# Kiểm tra readiness
curl -s http://localhost:8000/health/readiness | python3 -m json.tool

# Gửi webhook test
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

## Cấu trúc project

```
app/
├── server.py         # FastAPI endpoints + AppContainer wiring
├── orchestrator.py   # Pipeline engine (planning → coding → reviewing → state)
├── agents.py         # AgentsFacade — gọi CLI cho plan() và review()
├── config.py         # AppConfig với RolesConfig (per-role backend)
├── policy.py         # PolicyGuard — command/path allowlist
├── schemas.py        # TaskState, PipelineDecision, ExecutionConfig
├── store.py          # SQLite TaskStore + state machine
└── tools/
    ├── cli_executor.py   # Subprocess runner với timeout, fallback, auth hints
    ├── github_client.py  # GitHub API (comment, PR) với role-based PAT
    ├── repo_workspace.py # clone/pull workspace manager
    └── wiki_context.py   # WikiContextProvider interface
config/agent.yaml         # Roles, policy, repo, prompts, orchestrator settings
data/tasks.sqlite         # Task persistence (auto-created)
workspaces/               # Cloned target repos
```

## Cấu hình chi tiết (config/agent.yaml)

```yaml
roles:
  planner:
    backend: claude        # CLI binary name
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
  reviewer_changes_threshold: 1  # số lần CHANGES_REQUESTED trước khi → needs_human

policy:
  allowed_commands: [claude, codex, kiro-cli, gemini, git, uv, pytest]
  branch_prefix: "agent/"

repo:
  target_full_name: owner/repo
  clone_url: https://github.com/owner/repo.git
  local_path: workspaces/repo
  sync_on_task: true

execution:
  verify_commands:
    - "uv run pytest -q"   # chạy sau coding, stderr → CHANGES_REQUESTED
```

## Review Decision Protocol

Reviewer CLI nhận prompt yêu cầu output `APPROVED`, `CHANGES_REQUESTED`, hoặc `NEEDS_HUMAN` trên dòng đầu tiên. `AgentsFacade._parse_decision()` tìm keyword trong stdout.

```
APPROVED
Task completed correctly. README section added as requested.
```

## Tests

```bash
uv run pytest -q                                      # full suite (16 tests)
uv run pytest -q tests/test_orchestrator_integration.py  # integration only
```

## CLI Auth Check

```bash
# Claude
claude auth status
claude auth login    # nếu chưa login

# Codex
codex login status
codex login --device-auth

# Kiro (nếu dùng)
kiro-cli auth login

# Gemini (nếu dùng)
gemini auth login
```

Khi CLI chưa auth, orchestrator append login hint vào task stderr để operator biết cần làm gì.

## Ghi chú

- Coder delegate hoàn toàn cho CLI — không có logic viết code trong Python
- Reviewer phân tích output của coder và trả về decision dạng keyword
- Retry loop: CHANGES_REQUESTED → re-plan + re-code + re-review (không giữ state từ lần trước)
- GitHub comment chỉ hoạt động khi token được set
- `docs` và `memory` roles là optional — chưa được gọi trong pipeline hiện tại (hook điểm)
