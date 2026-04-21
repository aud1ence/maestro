from __future__ import annotations

import pytest

from app.schemas import TaskState


def test_idempotency_dedupe(temp_store):
    payload = {"issue": {"id": 1, "labels": [{"name": "agent"}]}, "repository": {"full_name": "o/r"}}
    first, created_first = temp_store.create_task_if_absent("task-1", "idem-1", payload)
    second, created_second = temp_store.create_task_if_absent("task-2", "idem-1", payload)

    assert created_first is True
    assert created_second is False
    assert first.id == second.id


def test_state_transition_guard(temp_store):
    payload = {"issue": {"id": 1, "labels": [{"name": "agent"}]}, "repository": {"full_name": "o/r"}}
    task, _ = temp_store.create_task_if_absent("task-1", "idem-1", payload)

    temp_store.transition_state(task.id, TaskState.PLANNING)

    with pytest.raises(ValueError):
        temp_store.transition_state(task.id, TaskState.COMPLETED)
