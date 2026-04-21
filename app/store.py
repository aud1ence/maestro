from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.schemas import TaskState


STATE_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.QUEUED: {TaskState.PLANNING, TaskState.FAILED, TaskState.NEEDS_HUMAN},
    TaskState.PLANNING: {TaskState.CODING, TaskState.FAILED, TaskState.NEEDS_HUMAN},
    TaskState.CODING: {TaskState.REVIEWING, TaskState.FAILED, TaskState.NEEDS_HUMAN},
    TaskState.REVIEWING: {TaskState.COMPLETED, TaskState.CODING, TaskState.FAILED, TaskState.NEEDS_HUMAN},
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
    TaskState.NEEDS_HUMAN: {TaskState.QUEUED},
}


@dataclass
class TaskRecord:
    id: str
    idempotency_key: str
    state: TaskState
    payload: dict[str, Any]
    retry_count: int
    last_error: str | None
    result_summary: str | None


class TaskStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    state TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    result_summary TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS tasks_updated_at
                AFTER UPDATE ON tasks
                BEGIN
                    UPDATE tasks SET updated_at=CURRENT_TIMESTAMP WHERE id=old.id;
                END;
                """
            )

    def create_task_if_absent(self, task_id: str, idempotency_key: str, payload: dict[str, Any]) -> tuple[TaskRecord, bool]:
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM tasks WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing:
                return self._row_to_record(existing), False

            conn.execute(
                """
                INSERT INTO tasks (id, idempotency_key, state, payload_json, retry_count)
                VALUES (?, ?, ?, ?, 0)
                """,
                (task_id, idempotency_key, TaskState.QUEUED.value, json.dumps(payload)),
            )
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            assert row is not None
            return self._row_to_record(row), True

    def get_task(self, task_id: str) -> TaskRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            return None
        return self._row_to_record(row)

    def transition_state(
        self,
        task_id: str,
        new_state: TaskState,
        *,
        last_error: str | None = None,
        result_summary: str | None = None,
        increment_retry: bool = False,
    ) -> TaskRecord:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not row:
                raise KeyError(f"Task {task_id} not found")
            current = TaskState(row["state"])
            allowed = STATE_TRANSITIONS[current]
            if new_state not in allowed:
                raise ValueError(f"Invalid state transition: {current.value} -> {new_state.value}")

            retry_count = int(row["retry_count"]) + (1 if increment_retry else 0)
            conn.execute(
                """
                UPDATE tasks
                SET state = ?, retry_count = ?, last_error = ?, result_summary = ?
                WHERE id = ?
                """,
                (new_state.value, retry_count, last_error, result_summary, task_id),
            )
            updated = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            assert updated is not None
            return self._row_to_record(updated)

    def reset_for_retry(self, task_id: str) -> TaskRecord:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not row:
                raise KeyError(f"Task {task_id} not found")
            current = TaskState(row["state"])
            if current not in {TaskState.NEEDS_HUMAN, TaskState.FAILED}:
                raise ValueError("Only failed/needs_human tasks can be retried")
            retry_count = int(row["retry_count"]) + 1
            conn.execute(
                "UPDATE tasks SET state = ?, retry_count = ?, last_error = NULL WHERE id = ?",
                (TaskState.QUEUED.value, retry_count, task_id),
            )
            updated = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            assert updated is not None
            return self._row_to_record(updated)

    def _row_to_record(self, row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(
            id=row["id"],
            idempotency_key=row["idempotency_key"],
            state=TaskState(row["state"]),
            payload=json.loads(row["payload_json"]),
            retry_count=int(row["retry_count"]),
            last_error=row["last_error"],
            result_summary=row["result_summary"],
        )
