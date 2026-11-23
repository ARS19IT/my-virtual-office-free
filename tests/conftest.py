"""pytest setup: the workflow E2E test drives a running office server."""
import os

collect_ignore = []
if not os.environ.get("VO_TEST_URL"):
    # Run it with: VO_TEST_URL=http://127.0.0.1:8090 pytest tests/test_workflow_e2e.py
    collect_ignore.append("test_workflow_e2e.py")
