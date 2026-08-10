#!/usr/bin/env python3
import json
import tempfile
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from task_board_outbox import TaskBoardOutbox


def test_idempotent_create_and_durable_update():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "outbox.json"
        first = {"type": "task.reassign", "idempotencyKey": "legacy-key", "status": "pending"}
        outbox = TaskBoardOutbox(path)
        saved, created = outbox.create(first)
        assert created is True
        command = {
            "commandId": "cmd-1", "projectId": "project-1", "taskId": "task-1",
            "from": "agent-a", "to": "agent-b", "actor": "user",
            "idempotencyKey": "key-1", "expectedVersion": 3,
            "requestHash": "hash-1", "status": "pending",
        }
        saved, created = outbox.create(command)
        assert created is True
        assert {"commandId", "projectId", "taskId", "from", "to", "actor",
                "idempotencyKey", "expectedVersion", "requestHash"} <= saved.keys()
        duplicate, created = outbox.create({**first, "status": "active"})
        assert created is False
        assert duplicate["status"] == "pending"
        duplicate, created = outbox.create({**command, "status": "active"})
        assert created is False
        assert duplicate["status"] == "pending"
        assert outbox.update("key-1", status="active")["status"] == "active"
        assert json.loads(path.read_text())[1]["status"] == "active"
        assert TaskBoardOutbox(path).lookup("key-1")["status"] == "active"


def test_remove_is_atomic_and_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "outbox.json"
        outbox = TaskBoardOutbox(path)
        outbox.create({"idempotencyKey": "keep", "status": "pending"})
        outbox.create({"idempotencyKey": "remove", "status": "pending"})

        assert outbox.remove("remove") is True
        assert outbox.lookup("remove") is None
        assert outbox.lookup("keep")["status"] == "pending"
        assert outbox.remove("remove") is False
        assert json.loads(path.read_text()) == [{"idempotencyKey": "keep", "status": "pending"}]


def test_claim_reclaims_expired_and_increments_attempts():
    with tempfile.TemporaryDirectory() as tmp:
        outbox = TaskBoardOutbox(Path(tmp) / "outbox.json")
        outbox.create({"idempotencyKey": "claim", "status": "pending"})
        first = outbox.claim_pending(now=100, retry_after=5)
        assert first["status"] == "active" and first["attempts"] == 1
        assert outbox.claim_pending(now=102) is None
        second = outbox.claim_pending(now=106, retry_after=5)
        assert second["status"] == "active" and second["attempts"] == 2


def test_failed_records_wait_until_retry_time():
    with tempfile.TemporaryDirectory() as tmp:
        outbox = TaskBoardOutbox(Path(tmp) / "outbox.json")
        outbox.create({"idempotencyKey": "retry", "status": "failed", "nextAttemptAt": 20})
        assert outbox.claim_pending(now=19) is None
        assert outbox.claim_pending(now=20)["attempts"] == 1


if __name__ == "__main__":
    test_idempotent_create_and_durable_update()
    test_remove_is_atomic_and_idempotent()
    print("task board outbox test passed")
