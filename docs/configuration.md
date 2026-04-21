# Configuration

## Environment Variables

```bash
# GitHub personal access token — repo scope covers issue comments and PR creation
GITHUB_TOKEN=

# Webhook HMAC secret — set in GitHub repo settings → Webhooks (optional, skipped if empty)
GITHUB_WEBHOOK_SECRET=

# CLI tools authenticate via their own OAuth/device auth flows
# Optional: use API key instead of device auth for codex
OPENAI_API_KEY=
```

## `config/agent.yaml` Reference

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

## Multi-repo Support

Any GitHub repository can trigger the agent — there is no hardcoded repo allowlist. Access control is via the HMAC webhook secret (`GITHUB_WEBHOOK_SECRET`). **Set this in production.**

When a webhook arrives, the orchestrator:
1. Verifies the HMAC signature (if `GITHUB_WEBHOOK_SECRET` is set)
2. Checks that the issue has the `agent` label
3. Clones or pulls the repo into `workspaces/<owner>/<repo>` (derived from `repository.full_name`)
4. Runs the full pipeline in that workspace

To add a new repo: install the webhook on that repo pointing to `POST /webhook/github`.

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
