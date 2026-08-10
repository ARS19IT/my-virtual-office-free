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
            # Task has a current assignee so None != "agent-a" triggers the
            # persistence path; a same-assignee request would short-circuit
            # before reaching _save_projects.
            "_load_projects": lambda: {"projects": [{
                "id": "project-1", "tasks": [{"id": "task-1", "version": 0, "assignee": "agent-a"}],
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
        # Unassign (None) from the current "agent-a" — different assignees,
        # so the save path is reached and the simulated OSError fires.
        result = namespace["_handle_task_board_assignment"](
            "project-1",
            "task-1",
            {"assignee": None, "expectedVersion": 0, "idempotencyKey": "failure-key"},
        )

        assert result["code"] == "assignment_failed"
        assert result["_status"] == 500
        # The outbox record must not have been created when persistence failed.
        assert outbox.lookup("failure-key") is None


def test_same_assignee_reassignment_returns_unchanged_no_outbox():
    """Repeated assignment to the same assignee returns unchanged without creating an outbox record."""
    with tempfile.TemporaryDirectory() as tmp:
        outbox = TaskBoardOutbox(Path(tmp) / "outbox.json")
        source = (Path(__file__).resolve().parents[1] / "app" / "server.py").read_text()
        function = next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name == "_handle_task_board_assignment"
        )
        namespace = {
            "TASK_BOARD_OUTBOX": outbox,
            "_load_projects": lambda: {"projects": [{
                "id": "project-1", "tasks": [{"id": "task-1", "version": 3, "assignee": "agent-a"}],
            }]},
            "_save_projects": lambda data: None,
            "_WORKFLOW_LOCK": threading.Lock(),
            "_WORKFLOW_STATE": {},
            "_proj_now": lambda: "2026-01-01T00:00:00+00:00",
            "_refresh_discovery": lambda: None,
            "_discovered_roster": [{"id": "agent-a"}],
            "hashlib": hashlib,
            "json": json,
            "uuid": uuid,
            "time": time,
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(Path(__file__)), "exec"), namespace)
        result = namespace["_handle_task_board_assignment"](
            "project-1",
            "task-1",
            {"assignee": "agent-a", "expectedVersion": 3, "idempotencyKey": "same-assignee-key"},
        )

        assert result["ok"] is True
        assert result["status"] == "unchanged"
        assert result["pending"] is False
        assert result["commandId"] is None
        assert result["expectedVersion"] == 3  # version unchanged
        # No outbox record created when assignee is unchanged.
        assert outbox.lookup("same-assignee-key") is None


def test_self_reassignment_is_skipped_after_type_normalization():
    source = (Path(__file__).resolve().parents[1] / "app" / "server.py").read_text()
    function = next(node for node in ast.parse(source).body
                    if isinstance(node, ast.FunctionDef) and node.name == "_dispatch_task_board_handoff")
    with tempfile.TemporaryDirectory() as tmp:
        outbox = TaskBoardOutbox(Path(tmp) / "outbox.json")
        sent = []
        namespace = {"TASK_BOARD_OUTBOX": outbox, "_handle_agent_platform_comm_send": lambda p: sent.append(p), "_task_board_command_message": lambda r: "test", "json": json}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(Path(__file__)), "exec"), namespace)
        record = {"from": 2, "to": "2", "idempotencyKey": "self", "commandId": "cmd"}
        outbox.create(record)
        result = namespace["_dispatch_task_board_handoff"](record)
        assert result["ok"] is True and result["skipped"] == "self-reassignment"
        assert sent == []


def test_partial_fan_out_skips_successful_targets_on_retry():
    """When one target in a fan-out succeeds and another fails, retry sends only to the failed target."""
    source = (Path(__file__).resolve().parents[1] / "app" / "server.py").read_text()
    tree = ast.parse(source)
    wanted = {"_dispatch_task_board_handoff", "_task_board_command_message"}
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]

    with tempfile.TemporaryDirectory() as tmp:
        outbox = TaskBoardOutbox(Path(tmp) / "outbox.json")
        sent = []

        def fake_send(payload):
            sent.append(payload)
            target = payload["toAgentId"]
            # agent-new succeeds; agent-old fails.
            if target == "agent-old":
                return {"ok": False, "error": "transport failure"}
            return {"ok": True, "messageId": "m-" + target}

        namespace = {
            "TASK_BOARD_OUTBOX": outbox,
            "_handle_agent_platform_comm_send": fake_send,
            "json": json,
        }
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(Path(__file__)), "exec"), namespace)

        record = {
            "type": "task.reassign", "projectId": "project-1", "taskId": "task-1",
            "from": "agent-old", "to": "agent-new", "actor": "user",
            "idempotencyKey": "partial-key", "commandId": "cmd-partial",
        }
        outbox.create(record)

        # First dispatch: agent-new succeeds, agent-old fails.
        result = namespace["_dispatch_task_board_handoff"](outbox.lookup("partial-key"))
        assert result["ok"] is False
        assert len(sent) == 2
        assert sent[0]["toAgentId"] == "agent-new"
        assert sent[1]["toAgentId"] == "agent-old"

        # Record now has one successful delivery.
        record_after_first = outbox.lookup("partial-key")
        deliveries = record_after_first.get("deliveries", [])
        assert len(deliveries) == 2
        assert deliveries[0]["target"] == "agent-new" and deliveries[0]["ok"] is True
        assert deliveries[1]["target"] == "agent-old" and deliveries[1]["ok"] is False

        # Simulate retry: agent-old now succeeds.
        def fake_send_retry(payload):
            sent.append(payload)
            return {"ok": True, "messageId": "m-" + payload["toAgentId"]}

        namespace["_handle_agent_platform_comm_send"] = fake_send_retry
        result_retry = namespace["_dispatch_task_board_handoff"](record_after_first)
        assert result_retry["ok"] is True
        # Only one new send: agent-old (agent-new was skipped).
        assert len(sent) == 3
        assert sent[2]["toAgentId"] == "agent-old"

        # Final record has two successful deliveries.
        record_final = outbox.lookup("partial-key")
        deliveries_final = record_final.get("deliveries", [])
        assert len(deliveries_final) == 3
        # The first two deliveries remain (agent-new success, agent-old failure),
        # and the third is the retry success for agent-old.
        assert deliveries_final[0]["target"] == "agent-new" and deliveries_final[0]["ok"] is True
        assert deliveries_final[1]["target"] == "agent-old" and deliveries_final[1]["ok"] is False
        assert deliveries_final[2]["target"] == "agent-old" and deliveries_final[2]["ok"] is True


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


def test_board_move_changes_column_once_and_rejects_stale_version():
    """Drag/drop moves are optimistic and never overwrite a newer card."""
    source = (Path(__file__).resolve().parents[1] / "app" / "server.py").read_text()
    function = next(node for node in ast.parse(source).body
                    if isinstance(node, ast.FunctionDef) and node.name == "_handle_task_board_move")
    projects = {"projects": [{"id": "p", "columns": [{"id": "todo"}, {"id": "doing"}],
                              "tasks": [{"id": "t", "columnId": "todo", "version": 2}]}]}
    saved = []
    namespace = {"_load_projects": lambda: projects, "_save_projects": lambda data: saved.append(data),
                 "_proj_now": lambda: "now"}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(Path(__file__)), "exec"), namespace)
    moved = namespace["_handle_task_board_move"]("p", "t", {"columnId": "doing", "expectedVersion": 2})
    assert moved["ok"] is True and moved["expectedVersion"] == 3
    assert projects["projects"][0]["tasks"][0]["columnId"] == "doing"
    assert len(saved) == 1
    stale = namespace["_handle_task_board_move"]("p", "t", {"columnId": "todo", "expectedVersion": 2})
    assert stale["_status"] == 409 and stale["code"] == "stale_version"
    assert projects["projects"][0]["tasks"][0]["columnId"] == "doing"


if __name__ == "__main__":
    test_assignment_round_trip_is_atomic_store_compatible()
    test_assignment_failure_removes_pending_outbox_record()
    test_handoff_dispatch_retry_ack_and_terminal_projection()
    print("task board store test passed")
