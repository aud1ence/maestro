# API Reference

## Endpoints

| Method | Path                | Description                            |
| ------ | ------------------- | -------------------------------------- |
| `POST` | `/webhook/github`   | Receive GitHub Issue webhook           |
| `GET`  | `/tasks/{id}`       | Get task state and result              |
| `POST` | `/tasks/{id}/retry` | Reset a `needs_human` task to `queued` |
| `GET`  | `/health`           | Liveness check                         |
| `GET`  | `/health/readiness` | CLI auth status + GitHub token check   |

## Examples

### Check readiness

```bash
curl -s http://localhost:8000/health/readiness | python3 -m json.tool
```

### Send a test webhook

```bash
curl -X POST http://localhost:8000/webhook/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Delivery: test-001" \
  -d '{
    "action": "labeled",
    "issue": {
      "id": 1, "number": 1,
      "title": "Fix bug",
      "body": "Details...",
      "labels": [{"name": "agent"}]
    },
    "repository": {"full_name": "owner/repo"},
    "sender": {"login": "user"}
  }'
```

### Poll a task

```bash
curl http://localhost:8000/tasks/<task_id> | python3 -m json.tool
```

### Retry a needs_human task

```bash
curl -X POST http://localhost:8000/tasks/<task_id>/retry
```
