import os
import sys
import tempfile
import unittest

os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-test-status-"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "app"))
import server  # noqa: E402


class StaticAllowlistTests(unittest.TestCase):
    def test_office_ui_assets_are_public(self):
        for path in ("/", "/index.html", "/game.js", "/style.css", "/favicon.svg",
                     "/icon-192.png", "/manifest.json", "/default-office-config.json",
                     "/cron.html", "/marked.min.js"):
            self.assertTrue(server._is_public_static_path(path), path)

    def test_source_scripts_and_secrets_are_not_served(self):
        for path in ("/vo-config.json", "/server.py", "/providers/codex.py",
                     "/providers/", "/entrypoint.sh", "/Dockerfile", "/.env",
                     "/.git/config", "/%2e%2e/pyproject.toml", "/a/../.env",
                     "/vo-config.json.bak", "/whisper-server.py"):
            self.assertFalse(server._is_public_static_path(path), path)


if __name__ == "__main__":
    unittest.main()
