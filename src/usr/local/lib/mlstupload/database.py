#! /usr/bin/python3

"Run information database handler - sqlite3 based"

import sqlite3

from . import common

SCHEMA = (
    "CREATE TABLE run "
    "(local text primary key, remote text unique, uploaded int)"
)


class RunDB:
    "Run Database class to handle run mapping information"

    def __init__(self, readonly: bool = False):
        assert common.CONFIG is not None, "Config not loaded before database"
        self.src = None
        self.conn = None
        self.readonly = readonly
        common.CONFIG.update_hook.add(self.reload)
        self.reload()

    def reload(self):
        "Update schema as needed and load it"
        # We are expecting no connections established to DB
        path = common.CONFIG["local"]["runid_db"]
        if self.src == path:
            # No need to reload. We still use the same DB
            return
        if self.conn is not None:
            # Changed database location. Clean up old one
            self.conn.rollback()
            self.conn.close()
            if common.VERBOSE:
                print("Previous database", self.src, "rolled back")
        self.conn = sqlite3.connect(path)
        cur = self.conn.cursor()
        check = cur.execute(
            "SELECT sql FROM sqlite_schema WHERE type=? AND name=?",
            ("table", "run")
        ).fetchone()
        if check and check[0] == SCHEMA:
            # Check passed. Rollback db and move on.
            self.conn.rollback()
            return
        if check and check[0] != SCHEMA:
            # Check failed - previous run table had a different schema
            if self.readonly:
                raise PermissionError(
                    "Cannot update schema due to read-only DB"
                )
            cur.execute("DROP TABLE run")
        # If we don't have the DB in the first place
        # we can still create the DB even in read-only mode.
        cur.execute(SCHEMA)
        self.conn.commit()

    def __enter__(self):
        # Activate the database
        return self.conn.cursor()

    def __exit__(self, err, *_):
        # Clean up the database connection
        if err is not None or self.readonly:
            self.conn.rollback()
        else:
            self.conn.commit()

    def get_run(self, local_id: str) -> tuple:
        "Get remote run id from local id, return None if not present"
        cur = self.conn.cursor()
        data = cur.execute(
            "SELECT remote,uploaded FROM run WHERE local=?", (local_id,)
        ).fetchone()
        self.conn.rollback()
        return data

    def create_run(self, local_id: str, remote_id: str):
        "Create a new run entry"
        assert not self.readonly, "Read only database"
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO run VALUES (?,?,?)", (local_id, remote_id, 0)
        )
        self.conn.commit()

    def increment_run(self, local_id: str) -> int:
        "Increment the number of files uploaded"
        assert not self.readonly, "Read only database"
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE run SET uploaded=uploaded+1 WHERE local=?", (local_id,)
        )
        data = cur.execute(
            "SELECT uploaded FROM run WHERE local=?", (local_id,)
        ).fetchone()[0]
        self.conn.commit()
        return data
