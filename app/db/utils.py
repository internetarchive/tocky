import sqlite3
from pathlib import Path

from tocky.env import get_env

env = get_env()


class DbContext:
    def __init__(self):
        self.conn = sqlite3.connect(env.TOCKY_QUEUE_DB_PATH)
        self.conn.row_factory = sqlite3.Row

    def __enter__(self):
        self.cursor = self.conn.cursor()
        self.cursor.execute("PRAGMA temp_store = MEMORY;")
        self.cursor.execute("PRAGMA cache_size = 10000;")
        self.cursor.execute("PRAGMA journal_mode = WAL;")
        return self.conn, self.cursor

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cursor.close()
        self.conn.close()


def init_db():
    with DbContext() as (conn, cur):
        # Run init sql if table does not exist
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='toc_queue'"
        )
        result = cur.fetchone()
        if not result:
            schema_sql = (Path(__file__).parent / "schema.sql").read_text()
            cur.executescript(schema_sql)

