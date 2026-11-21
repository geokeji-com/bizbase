"""Portable contract for the BizBase application identities and public route registry."""
import json
import re
import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APPS = ROOT / "apps"
SCREEN = runpy.run_path(str(APPS / "management_board/management_board/apps_screen.py"))


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
                aliases = site["bizbase_workspace_aliases"]
                for name in set(aliases.values()):
                    workspace, = hooks.parent.glob("*/workspace/*/*.json")
                    self.assertEqual(json.loads(workspace.read_text())["name"], name)
                    self.assertEqual(aliases[name.replace("_", "-")], name)
                for path in hooks.parent.glob("*/doctype/*/*.json"):
                    doc = json.loads(path.read_text())
                    self.assertRegex(doc["name"], r"^[A-Z][A-Za-z0-9]*(?: [A-Z][A-Za-z0-9]*)*$")
                    self.assertEqual(path.stem, doc["name"].lower().replace(" ", "_"))
                    for field in doc["fields"]:
                        self.assertTrue(re.fullmatch(r"[a-z][a-z0-9_]*", field["fieldname"]), field)

    def test_four_role_boards_share_the_same_identity_scheme(self):
        boards = {"management_board": "管理看板", "sales_board": "销售看板",
                  "ops_board": "运营看板", "customer_board": "客户看板"}
        self.assertEqual(SCREEN["WORKSPACE_APPS"], set(boards))
        for app, title in boards.items():
            with self.subTest(app=app):
                package = APPS / app / app
                self.assertEqual(runpy.run_path(str(package / "hooks.py"))["app_title"], title)
                self.assertEqual((package / "modules.txt").read_text().strip(), app)
                workspace = json.loads((package / app / "workspace" / app / f"{app}.json").read_text())
                self.assertEqual((workspace["module"], workspace["name"]), (app, app))

    def test_management_board_card_and_bookmarks(self):
        site = {"app_data": [{"app_name": "management_board", "app_route": "/desk/management_board"}]}
        SCREEN["apply"](site)
        card, = site["app_data"]
        self.assertEqual((card["sequence_id"], card["app_route"]), (3, "/desk/management-board"))
        self.assertEqual(site["bizbase_workspace_aliases"],
                         dict.fromkeys(("management-board", "bizbase-mgmt", "bizbase_mgmt"), "management_board"))

    def test_registry_preserves_custom_landings_and_only_installed_apps(self):
        site = {"app_data": [{"app_name": "ops_board", "app_route": "/my-home"},
                             {"app_name": "third_party", "app_route": "/desk/third_party"}]}
        SCREEN["apply"](site)
        self.assertEqual(site["bizbase_workspace_aliases"], {"ops-board": "ops_board"})
        self.assertEqual([app["app_route"] for app in site["app_data"]], ["/my-home", "/desk/third_party"])


if __name__ == "__main__":
    unittest.main()
