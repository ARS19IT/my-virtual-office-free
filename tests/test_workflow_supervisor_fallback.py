import ast
from pathlib import Path


SERVER_PATH = Path(__file__).resolve().parents[1] / "app" / "server.py"


def _function_source(name):
    tree = ast.parse(SERVER_PATH.read_text(encoding="utf-8"))
    node = next(
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )
    return ast.get_source_segment(SERVER_PATH.read_text(encoding="utf-8"), node)


def test_supervisor_fallback_uses_gateway_routed_main_session():
    source = _function_source("_wf_supervisor_spawn_children")
    assert '_wf_call_agent("main"' in source
    assert "sessions_spawn" in source
    assert "runId" in source and "sessionKey" in source
    assert "task text: task_id=" in source
    assert "parentTaskId=" in source
    assert "Do not add task_id or parentTaskId as sessions_spawn arguments" in source
    assert "Each sessions_spawn call must include task_id and parentTaskId" not in source
    assert "_wf_call_agent_cli" not in source


def test_worker_prompt_does_not_authorize_worker_spawning():
    source = _function_source("_wf_build_task_prompt")
    assert "supervisor/main process is solely responsible" in source
    assert "accept and track these assignments" in source
    assert "YOU MUST DELEGATE THESE USING" not in source


def test_pipeline_does_not_accept_worker_spawn_transcript_as_authority():
    source = _function_source("_wf_run_pipeline_inner")
    assert "_wf_supervisor_spawn_children(project_id, task, child_tasks)" in source
    assert "spawn_calls = work_activity.get(\"spawn_calls\", [])" not in source
