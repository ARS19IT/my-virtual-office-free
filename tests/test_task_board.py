#!/usr/bin/env python3
"""Focused checks for the task-board projection and assignment seam."""
import ast
import hashlib
import json
import tempfile
import threading
import uuid
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from project_store import MarkdownProjectStore
from task_board_outbox import TaskBoardOutbox


def test_assignment_round_trip_is_atomic_store_compatible():
    with tempfile.TemporaryDirectory() as tmp:
        store = MarkdownProjectStore(tmp)
        project = {
            "id": "project-1", "title": "Board", "columns": [{"id": "todo", "title": "Todo"}],
            "tasks": [{"id": "task-1", "title": "Ship", "columnId": "todo", "assignee": "agent-a",
                       "checklist": [{"id": "cp-1", "text": "Test", "done": True}]}],
        }
        store.save_all({"projects": [project], "templates": []})
        loaded = store.get_project("project-1")
        assert loaded["tasks"][0]["assignee"] == "agent-a"
        assert loaded["tasks"][0]["checklist"][0]["done"] is True
        project["tasks"][0]["assignee"] = "agent-b"
        store.save_all({"projects": [project], "templates": []})
        assert store.get_project("project-1")["tasks"][0]["assignee"] == "agent-b"


def test_assignment_failure_removes_pending_outbox_record():
    with tempfile.TemporaryDirectory() as tmp:
        outbox = TaskBoardOutbox(Path(tmp) / "outbox.json")
        source = (Path(__file__).resolve().parents[1] / "app" / "server.py").read_text()
        function = next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name == "_handle_task_board_assignment"
        )
        def _raise(*a, **kw):
            raise OSError("simulated project persistence failure")
        namespace = {
            "TASK_BOARD_OUTBOX": outbox,
            "_load_projects": lambda: {"projects": [{
                "id": "project-1", "tasks": [{"id": "task-1", "version": 0, "assignee": None}],
            }]},
            "_save_projects": _raise,
            "_handle_task_update": _raise,
            "_WORKFLOW_LOCK": threading.Lock(),
            "_WORKFLOW_STATE": {},
            "_proj_now": lambda: "2026-01-01T00:00:00+00:00",
            "_refresh_discovery": lambda: None,
            "_discovered_roster": [],
            "hashlib": hashlib,
            "json": json,
            "uuid": uuid,
            "time": time,
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(Path(__file__)), "exec"), namespace)
        result = namespace["_handle_task_board_assignment"](
            "project-1",
            "task-1",
            {"assignee": None, "expectedVersion": 0, "idempotencyKey": "failure-key"},
        )

        assert result["code"] == "assignment_failed"
        assert result["_status"] == 500
        assert outbox.lookup("failure-key") is None


def test_handoff_dispatch_retry_ack_and_terminal_projection():
    source = (Path(__file__).resolve().parents[1] / "app" / "server.py").read_text()
    tree = ast.parse(source)
    wanted = {"_task_board_command_message", "_dispatch_task_board_handoff",
              "_consume_task_board_outbox_once", "_handle_task_board_handoff",
              "_handle_task_board_handoff_ack", "_handle_task_board"}
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]

    with tempfile.TemporaryDirectory() as tmp:
        outbox = TaskBoardOutbox(Path(tmp) / "outbox.json")
        sent = []
        # The new assignee succeeds on the first attempt; the old-assignee
        # notification fails, so retry coverage proves successful deliveries
        # are not duplicated.
        fail_once = {"agent-old"}

        def fake_send(payload):
            sent.append(payload)
            target = payload["toAgentId"]
            if target in fail_once:
                fail_once.remove(target)
                return {"ok": False, "error": "temporary transport failure"}
            return {"ok": True, "messageId": "m-" + target}

        def load_projects():
            return {"projects": [{"id": "project-1", "title": "Board",
                "columns": [{"id": "todo", "title": "Todo"}],
                "tasks": [{"id": "task-1", "title": "Ship", "columnId": "todo"}]}]}

        namespace = {
            "TASK_BOARD_OUTBOX": outbox, "_handle_agent_platform_comm_send": fake_send,
            "json": json, "time": time, "_proj_now": lambda: "now",
            "_load_projects": load_projects,
        }
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(Path(__file__)), "exec"), namespace)
        record = {"type": "task.reassign", "projectId": "project-1", "taskId": "task-1",
                  "from": "agent-old", "to": "agent-new", "actor": "user",
                  "idempotencyKey": "key-1", "commandId": "cmd-1", "status": "pending"}
        outbox.create(record)

        first = namespace["_consume_task_board_outbox_once"]()
        assert first["status"] == "failed" and first["attempts"] == 1
        assert len(sent) == 2 and sent[0]["conversationId"] == "cmd-1"
        # Make the failed command immediately eligible for this deterministic test.
        outbox.update("key-1", nextAttemptAt=0)
        second = namespace["_consume_task_board_outbox_once"]()
        assert second["status"] == "completed" and second["attempts"] == 2
        assert len(sent) == 3
        assert [payload["toAgentId"] for payload in sent] == ["agent-new", "agent-old", "agent-old"]
        assert namespace["_consume_task_board_outbox_once"]() is None

        same = namespace["_handle_task_board_handoff_ack"]("cmd-1", {"status": "completed"})
        assert same["handoff"] == second
        conflict = namespace["_handle_task_board_handoff_ack"]("cmd-1", {"status": "failed"})
        assert conflict["_status"] == 409

        projection = namespace["_handle_task_board"]()
        assert projection["tasks"][0]["handoff"]["status"] == "completed"


if __name__ == "__main__":
    test_assignment_round_trip_is_atomic_store_compatible()
    test_assignment_failure_removes_pending_outbox_record()
    test_handoff_dispatch_retry_ack_and_terminal_projection()
    print("task board store test passed")
