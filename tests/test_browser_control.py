import base64
import json
import os
import sys
import ast
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import browser_control


class BrowserControlTests(unittest.TestCase):
    def setUp(self):
        self.config = {"features": {"browserPanel": True}, "browser": {"actionToken": "secret"}}

    def test_requires_broker_token(self):
        self.assertFalse(browser_control.authorize({}, self.config))
        self.assertTrue(browser_control.authorize({"Authorization": "Bearer secret"}, self.config))
        self.assertTrue(browser_control.authorize({"X-Virtual-Office-Browser-Token": "secret"}, self.config))

    def test_rejects_bad_navigation_scheme(self):
        with patch.object(browser_control, "_feature_allowed", return_value=True), patch.object(browser_control, "_json_tabs", return_value=[{"type": "page", "id": "p", "webSocketDebuggerUrl": "ws://x"}]):
            result = browser_control.action(self.config, {"action": "navigate", "url": "file:///etc/passwd"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], 400)

    def test_gate_is_preserved(self):
        with patch.object(browser_control, "_feature_allowed", return_value=False):
            result = browser_control.action(self.config, {"action": "status"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], 403)

    def test_http_dispatch_post_only(self):
        # Parse the handler dispatch so moving this route back into do_GET is a
        # regression caught even in a minimal test environment without server deps.
        server_path = Path(__file__).resolve().parents[1] / "app" / "server.py"
        tree = ast.parse(server_path.read_text())
        handler = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == "OfficeHandler"
        )
        methods = {
            node.name: node for node in handler.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        def has_browser_route(method):
            return any(
                isinstance(node, ast.Constant) and node.value == "/api/browser/action"
                for node in ast.walk(method)
            )

        self.assertTrue(has_browser_route(methods["do_POST"]))
        self.assertFalse(has_browser_route(methods["do_GET"]))


if __name__ == "__main__":
    unittest.main()
