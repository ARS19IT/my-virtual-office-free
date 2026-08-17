import json
import os
import sys
import tempfile
import unittest

TMP_STATUS_DIR = tempfile.mkdtemp(prefix="vo-test-status-")
os.environ.setdefault("VO_STATUS_DIR", TMP_STATUS_DIR)

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app")
sys.path.insert(0, APP_DIR)
import server  # noqa: E402


class OfficeConfigMigrationTests(unittest.TestCase):
    def test_legacy_branches_and_empty_assignments_are_canonicalized(self):
        cfg = {
            "canvasWidth": 1000,
            "furniture": [{"id": "kept", "type": "desk", "x": 10, "y": 10}],
            "branches": [{"id": "BRANCH_1", "name": "Branch #1"}, {"id": "BRANCH_2", "name": "Branch #2"}],
            "agents": [{"id": "2", "branch": "UNASSIGNED"}, {"id": "main", "branch": "CEO"}],
        }
        migrated = server._canonicalize_office_config(cfg)
        self.assertEqual([b["id"] for b in migrated["branches"]], ["CEO", "MAIN_TEAM", "OPS_TEAM"])
        self.assertEqual({a["id"]: a["branch"] for a in migrated["agents"]}, {"2": "MAIN_TEAM", "main": "CEO"})
        self.assertEqual({a["id"]: a["name"] for a in migrated["agents"]}, {"2": "Сэм", "main": "Кентик"})
        self.assertEqual({a["id"]: a["role"] for a in migrated["agents"]}, {"2": "аналитик", "main": "Босс"})
        self.assertEqual(migrated["furniture"][0]["id"], "kept")

    def test_load_reads_persisted_layout_without_legacy_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = {"canvasWidth": 1234, "furniture": [{"id": "user-desk"}], "branches": [{"id": "BRANCH_1"}], "agents": [{"id": "team", "branch": "UNASSIGNED"}]}
            with open(os.path.join(tmp, "office-config.json"), "w") as f:
                json.dump(payload, f)
            with self._patch_status_dir(tmp):
                loaded = server._load_office_config()
            self.assertEqual(loaded["canvasWidth"], 1234)
            self.assertEqual(loaded["furniture"][0]["id"], "user-desk")
            self.assertEqual(loaded["agents"][0]["branch"], "MAIN_TEAM")
            self.assertNotIn("BRANCH_1", [b["id"] for b in loaded["branches"]])

    def test_canonical_roster_metadata_for_all_agents(self):
        cfg = {"agents": [{"id": key} for key in ("main", "2", "team", "dising", "memory", "worker", "designer")]}
        migrated = server._canonicalize_office_config(cfg)
        actual = {a["id"]: (a["name"], a["role"], a["branch"]) for a in migrated["agents"]}
        self.assertEqual(actual, {
            "main": ("Кентик", "Босс", "CEO"),
            "2": ("Сэм", "аналитик", "MAIN_TEAM"),
            "team": ("Ден", "разработчик", "MAIN_TEAM"),
            "dising": ("Бухгалтер", "бухгалтер", "MAIN_TEAM"),
            "memory": ("Memory", "Memory", "OPS_TEAM"),
            "worker": ("Worker", "Worker", "OPS_TEAM"),
            "designer": ("Designer", "Designer", "OPS_TEAM"),
        })

    class _patch_status_dir:
        def __init__(self, value):
            self.value = value
        def __enter__(self):
            self.old = server.STATUS_DIR
            server.STATUS_DIR = self.value
        def __exit__(self, *args):
            server.STATUS_DIR = self.old


if __name__ == "__main__":
    unittest.main()
