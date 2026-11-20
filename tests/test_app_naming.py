"""Portable contract for the BizBase application identities and public route registry."""
import json
import re
import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APPS = ROOT / "apps"
SCREEN = runpy.run_path(str(APPS / "bizbase_mgmt/bizbase_mgmt/apps_screen.py"))


class NamingTest(unittest.TestCase):
    def test_app_id_products_and_workspace_identity(self):
        for hooks in APPS.glob("*/*/hooks.py"):
            with self.subTest(app=hooks.parent.name):
                config = runpy.run_path(str(hooks))
                app = config["app_name"]
                self.assertRegex(app, r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
                self.assertEqual((app, app), (hooks.parent.name, hooks.parent.parent.name))
                card, = config["add_to_apps_screen"]
                self.assertEqual(card["name"], app)
                self.assertEqual(card["title"], config["app_title"])
                self.assertNotIn("_", card["title"])
                self.assertNotEqual(card["title"], app)
                site = {"app_data": [{"app_name": app, "app_route": card["route"]}]}
                SCREEN["apply"](site)
                self.assertRegex(site["app_data"][0]["app_route"], r"^/(?:[a-z0-9-]+/)*[a-z0-9-]+$")
                for slug, name in site["bizbase_workspace_aliases"].items():
                    workspace, = hooks.parent.glob("*/workspace/*/*.json")
                    self.assertEqual(json.loads(workspace.read_text())["name"], name)
                    self.assertEqual(slug, name.replace("_", "-"))
                for path in hooks.parent.glob("*/doctype/*/*.json"):
                    doc = json.loads(path.read_text())
                    self.assertRegex(doc["name"], r"^[A-Z][A-Za-z0-9]*(?: [A-Z][A-Za-z0-9]*)*$")
                    self.assertEqual(path.stem, doc["name"].lower().replace(" ", "_"))
                    for field in doc["fields"]:
                        self.assertTrue(re.fullmatch(r"[a-z][a-z0-9_]*", field["fieldname"]), field)

    def test_registry_preserves_custom_landings_and_only_installed_apps(self):
        site = {"app_data": [{"app_name": "ops_board", "app_route": "/my-home"},
                             {"app_name": "third_party", "app_route": "/desk/third_party"}]}
        SCREEN["apply"](site)
        self.assertEqual(site["bizbase_workspace_aliases"], {"ops-board": "ops_board"})
        self.assertEqual([app["app_route"] for app in site["app_data"]], ["/my-home", "/desk/third_party"])


if __name__ == "__main__":
    unittest.main()
