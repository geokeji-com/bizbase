"""Integration rehearsal on a disposable copy of the *old* PG database, never a real site.

In the bench Python environment sharing the throwaway PG's loopback interface:
FILE_SHARE_RENAME_REHEARSAL=1 python -m unittest discover -s deploy/prod -p test_rename_file_share.py
The copy must be named file_share_rename_rehearsal. Pinned host/database/user, no DSN overrides.
"""

import json
import os
import unittest


@unittest.skipUnless(os.getenv("FILE_SHARE_RENAME_REHEARSAL") == "1", "requires disposable old-site PG copy")
class FileShareRename(unittest.TestCase):
    def test_data_permissions_collisions_and_retry(self):
        import psycopg2
        from psycopg2 import sql
        from rename_file_share import migrate

        conn = psycopg2.connect(
            host="127.0.0.1", port=5432, user="postgres", dbname="file_share_rename_rehearsal"
        )
        self.addCleanup(conn.close)
        cur = conn.cursor()

        def value(query, params=()):
            cur.execute(query, params)
            return cur.fetchone()[0]

        def seed(table, **fields):
            cur.execute(
                sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                    sql.Identifier(table),
                    sql.SQL(",").join(map(sql.Identifier, fields)),
                    sql.SQL(",").join([sql.Placeholder()] * len(fields)),
                ),
                list(fields.values()),
            )

        self.assertEqual(value("SELECT current_database()"), "file_share_rename_rehearsal")
        self.assertEqual(
            value("SELECT app_name FROM \"tabModule Def\" WHERE name='Static Share'"), "static_share"
        )
        marker = "RenamePG01"
        seed(
            "tabStatic Share",
            name=marker,
            title="rename-fixture",
            access_level="Password",
            current_version=2,
            access_salt="test-salt",
            upload="/private/files/archive.zip",
            share_url="/file-share/" + marker,
        )
        child = dict(name=marker, parenttype="Static Share", parent=marker)
        seed("tabStatic Share Role", **child, parentfield="allowed_roles", role="Desk User")
        seed("tabStatic Share User", **child, parentfield="allowed_users", user="Administrator")
        seed(
            "tabStatic Share Version",
            **child,
            parentfield="versions",
            version=2,
            entry="index.html",
            source_file=marker,
        )
        seed("tabStatic Share Access Log", name=marker, share=marker, version=2, result="Viewed")
        seed(
            "__Auth",
            doctype="Static Share",
            name=marker,
            fieldname="password",
            password="opaque-test-ciphertext",
            encrypted=1,
        )
        seed(
            "tabFile",
            name=marker,
            file_url="/private/files/archive.zip",
            is_private=1,
            attached_to_doctype="Static Share",
            attached_to_name=marker,
        )
        seed(
            "tabDocShare",
            name=marker,
            user="Administrator",
            share_doctype="Static Share",
            share_name=marker,
            read=1,
            write=0,
        )
        seed(
            "tabBlock Module",
            name=marker,
            module="Static Share",
            parenttype="User",
            parent="Guest",
            parentfield="block_modules",
        )
        seed("tabVersion", name=marker, ref_doctype="Static Share", docname=marker, data='{"changed":[]}')
        seed(
            "tabDesktop Layout",
            name=marker,
            layout=json.dumps([dict(app="static_share", link="/desk/static-share/" + marker)]),
        )
        seed("tabCustom DocPerm", name=marker, parent="Static Share", role="System Manager", read=1)
        conn.commit()

        with self.assertRaisesRegex(RuntimeError, "维护模式"):
            migrate(conn, "public", 0)
        cur.execute('CREATE TABLE "tabFile Share" (name text)')
        conn.commit()
        with self.assertRaisesRegex(RuntimeError, "目标表"):
            migrate(conn, "public", 1)
        cur.execute('DROP TABLE "tabFile Share"')
        seed(
            "tabDocShare",
            name="OrphanGrant",
            share_doctype="File Share",
            share_name=marker,
            everyone=1,
            read=1,
        )
        conn.commit()
        with self.assertRaisesRegex(RuntimeError, "未归属"):
            migrate(conn, "public", 1)
        cur.execute("DELETE FROM \"tabDocShare\" WHERE name='OrphanGrant'")
        # A late DDL error must undo all preceding metadata AND table renames.
        cur.execute('CREATE TABLE "tabFile Share Version_pkey" (name text)')
        conn.commit()
        with self.assertRaises(psycopg2.Error):
            migrate(conn, "public", 1)
        self.assertEqual(value("SELECT module FROM \"tabDocType\" WHERE name='Static Share'"), "Static Share")
        self.assertEqual(
            value('SELECT share_doctype FROM "tabDocShare" WHERE name=%s', (marker,)), "Static Share"
        )
        self.assertEqual(value('SELECT count(*) FROM "tabStatic Share" WHERE name=%s', (marker,)), 1)
        cur.execute('DROP TABLE "tabFile Share Version_pkey"')
        conn.commit()

        self.assertTrue(migrate(conn, "public", 1))
        self.assertFalse(migrate(conn, "public", 1))

        def expect(table, columns, values):
            cur.execute(
                sql.SQL("SELECT {} FROM {} WHERE name=%s").format(
                    sql.SQL(",").join(map(sql.Identifier, columns)), sql.Identifier(table)
                ),
                (marker,),
            )
            self.assertEqual(cur.fetchone(), values)

        expect(
            "tabFile Share",
            ["access_level", "current_version", "access_salt", "upload", "share_url"],
            ("Password", 2, "test-salt", "/private/files/archive.zip", "/file-share/" + marker),
        )
        expect(
            "tabFile Share Version",
            ["parenttype", "parent", "version", "entry", "source_file"],
            ("File Share", marker, 2, "index.html", marker),
        )
        expect("tabFile Share Role", ["parenttype", "parent", "role"], ("File Share", marker, "Desk User"))
        expect(
            "tabFile Share User", ["parenttype", "parent", "user"], ("File Share", marker, "Administrator")
        )
        expect("tabFile Share Access Log", ["share", "version", "result"], (marker, 2, "Viewed"))
        expect(
            "tabFile", ["attached_to_doctype", "attached_to_name", "is_private"], ("File Share", marker, 1)
        )
        expect("tabDocShare", ["share_doctype", "share_name", "read", "write"], ("File Share", marker, 1, 0))
        expect("tabCustom DocPerm", ["parent", "role", "read"], ("File Share", "System Manager", 1))
        expect("tabBlock Module", ["module", "parent"], ("File Share", "Guest"))
        expect("tabVersion", ["ref_doctype", "docname", "data"], ("File Share", marker, '{"changed":[]}'))
        expect(
            "__Auth",
            ["doctype", "fieldname", "password", "encrypted"],
            ("File Share", "password", "opaque-test-ciphertext", 1),
        )
        self.assertEqual(
            json.loads(value('SELECT layout FROM "tabDesktop Layout" WHERE name=%s', (marker,))),
            [dict(app="file_share", link="/desk/file-share/" + marker)],
        )
        self.assertEqual(
            value("SELECT options FROM \"tabDocField\" WHERE parent='File Share' AND fieldname='versions'"),
            "File Share Version",
        )
        self.assertEqual(value("SELECT count(*) FROM \"tabDocType\" WHERE module='File Share'"), 5)
        self.assertTrue(
            value(
                'SELECT EXISTS(SELECT 1 FROM "tabPatch Log" WHERE patch=%s)',
                ("static_share.migrate_file_share",),
            )
        )
        self.assertFalse(
            value(
                'SELECT EXISTS(SELECT 1 FROM "tabPatch Log" WHERE patch=%s)',
                ("file_share.migrate_file_share",),
            )
        )
        apps = json.loads(
            value(
                "SELECT defvalue FROM \"tabDefaultValue\" WHERE parent='__global' AND defkey='installed_apps'"
            )
        )
        self.assertIn("file_share", apps)
        self.assertNotIn("static_share", apps)
