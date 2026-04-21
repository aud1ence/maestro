# Deploying on Raspberry Pi 5

## Prerequisites

| Requirement | Minimum                           | Notes                                                   |
| ----------- | --------------------------------- | ------------------------------------------------------- |
| Hardware    | Raspberry Pi 5 (4 GB RAM)         | 8 GB recommended for running multiple CLIs concurrently |
| OS          | Raspberry Pi OS Bookworm (64-bit) | ARM64 — required for Node.js CLI tools                  |
| Storage     | 16 GB SD card or SSD              | SSD strongly recommended for workspace I/O              |
| Network     | Static IP or DDNS                 | Needed for GitHub webhook delivery                      |

---

## 1. System Setup

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl build-essential
```

### Python 3.11+

Bookworm ships Python 3.11. Verify:

```bash
python3 --version   # must be >= 3.11
```

### uv (Python package manager)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc   # or restart shell
uv --version
```

### Node.js 20+ (required for claude and codex CLIs)

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
node --version   # must be >= 20
```

---

## 2. Install CLI Tools

All CLIs run as the deployment user (not root).

### Claude Code CLI

```bash
npm install -g @anthropic-ai/claude-code
claude --version
claude auth login   # follow browser/device URL prompt
claude auth status  # verify: "loggedIn": true
```

### Codex CLI

```bash
npm install -g @openai/codex
codex --version
codex login --device-auth   # follow browser URL prompt
codex login status          # verify: "Logged in"
```

### kiro-cli (optional — Planner / Memory roles)

```bash
npm install -g kiro-cli   # adjust if package name differs
kiro-cli --version
kiro-cli auth login
```

### gemini (optional — Docs role)

```bash
npm install -g @google/gemini-cli   # adjust if package name differs
gemini --version
gemini auth login
```

> **ARM64 note:** All tools above are distributed as Node.js packages and run natively on ARM64. If a binary-only CLI is needed in the future, check for an `linux-arm64` release asset before installing.

---

## 3. Install the Orchestrator

```bash
git clone https://github.com/aud1ence/pi5-sdk-orchestrator.git
cd pi5-sdk-orchestrator
uv sync
```

---

## 4. Configure Environment

```bash
cp .env.example .env
nano .env
```

Minimum required:

```bash
GITHUB_TOKEN=ghp_...          # PAT with repo scope
GITHUB_WEBHOOK_SECRET=...     # random string — must match GitHub webhook config
```

Set the webhook secret with a strong random value:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## 5. Configure the Agent

Edit `config/agent.yaml`. At minimum, set the roles you intend to use:

```yaml
roles:
  planner:
    backend: claude
  coder:
    backend: claude
    fallback_backend: codex
    flags: ["--allowedTools", "Bash,Read,Write,Edit"]
  reviewer:
    backend: codex

policy:
  allowed_commands: [claude, codex, git, uv, pytest]

repo:
  sync_on_task: true
```

---

## 6. Expose the Webhook Endpoint

GitHub must be able to reach `POST /webhook/github`. Options:

### Option A — ngrok (development / testing)

```bash
# Install ngrok
curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
sudo apt update && sudo apt install ngrok
ngrok config add-authtoken <your_token>

# Run (in a separate terminal or as a service)
ngrok http 8000
```

Copy the `https://....ngrok-free.app` URL for the GitHub webhook.

### Option B — Port forwarding (production)

Forward port 443 → 8000 on your router, use a DDNS provider (e.g., DuckDNS), and optionally terminate TLS with nginx + certbot.

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

---

## 7. Register the GitHub Webhook

For each repo you want the agent to handle:

1. Go to **Settings → Webhooks → Add webhook**
2. Payload URL: `https://<your-domain>/webhook/github`
3. Content type: `application/json`
4. Secret: same value as `GITHUB_WEBHOOK_SECRET` in `.env`
5. Events: **Issues** only (or "Let me select individual events" → check Issues)

---

## 8. Run as a systemd Service

Create the service file:

```bash
sudo nano /etc/systemd/system/pi5-orchestrator.service
```

```ini
[Unit]
Description=pi5-sdk-orchestrator
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/pi5-sdk-orchestrator
EnvironmentFile=/home/pi/pi5-sdk-orchestrator/.env
ExecStart=/home/pi/.local/bin/uv run uvicorn app.server:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Adjust `User` and `WorkingDirectory` to match your setup. Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable pi5-orchestrator
sudo systemctl start pi5-orchestrator
sudo systemctl status pi5-orchestrator
```

View logs:

```bash
journalctl -u pi5-orchestrator -f
```

---

## 9. Verify Deployment

```bash
# Liveness
curl http://localhost:8000/health

# Full readiness — all CLIs authenticated + GITHUB_TOKEN set
curl http://localhost:8000/health/readiness | python3 -m json.tool
```

Expected readiness response when healthy:

```json
{
  "status": "ok",
  "cli": {
    "claude": { "authenticated": true, ... },
    "codex":  { "authenticated": true, ... }
  },
  "github": { "configured": true, "token_env": "GITHUB_TOKEN" }
}
```

---

## 10. Trigger a Test Task

Label any issue in a watched repo with **`agent`**. The orchestrator will:

1. Receive the webhook
2. Clone / pull the repo into `workspaces/<owner>/<repo>`
3. Run planning → coding → reviewing
4. Comment the result on the issue (if `GITHUB_TOKEN` is set)

Alternatively, send a manual webhook (no signature needed if `GITHUB_WEBHOOK_SECRET` is commented out):

```bash
curl -X POST http://localhost:8000/webhook/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Delivery: test-001" \
  -d '{
    "action": "labeled",
    "issue": {
      "id": 1, "number": 1,
      "title": "Add hello world to README",
      "body": "Add a ## Hello World section.",
      "labels": [{"name": "agent"}]
    },
    "repository": {
      "full_name": "your-org/your-repo",
      "clone_url": "https://github.com/your-org/your-repo.git"
    },
    "sender": {"login": "you"}
  }'
```

Poll the task:

```bash
curl http://localhost:8000/tasks/<task_id> | python3 -m json.tool
```

---

## Troubleshooting

| Symptom                                   | Likely cause                          | Fix                                                                         |
| ----------------------------------------- | ------------------------------------- | --------------------------------------------------------------------------- |
| `"authenticated": false` for claude       | Not logged in                         | `claude auth login`                                                         |
| `"authenticated": false` for codex        | Not logged in                         | `codex login --device-auth`                                                 |
| `"configured": false` for github          | `GITHUB_TOKEN` missing                | Set in `.env`                                                               |
| Webhook returns 401                       | HMAC mismatch                         | Check `GITHUB_WEBHOOK_SECRET` matches GitHub webhook config                 |
| Webhook returns 400 `missing agent label` | Issue not labeled                     | Add `agent` label to the issue                                              |
| Task stuck in `planning` or `coding`      | CLI timeout (default 900s)            | Check `journalctl` for subprocess errors                                    |
| `workspaces/` not created                 | `sync_on_task: false` or clone failed | Check git credentials / network                                             |
| `needs_human` after 1 retry               | Reviewer threshold reached            | Increase `reviewer_changes_threshold` or retry via `POST /tasks/<id>/retry` |
