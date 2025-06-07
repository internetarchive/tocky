import json
import sqlite3
from pathlib import Path
from typing import Sequence

from fastapi import Request
from fastapi.responses import JSONResponse

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


def db_select_from_params(
    table: str,
    filter_fields: Sequence[str],
    sort_fields: Sequence[str],
    limit: int,
    offset: int,
    sort: str,
    request: Request,
):
    direction = 'DESC' if sort[0] == '-' else 'ASC'
    sort_field = sort.lstrip('-')
    if sort_field not in sort_fields:
        return JSONResponse({'success': False, 'message': 'Invalid sort field'}, status_code=400)
    where_clauses = []
    params = []

    for list_field in filter_fields:
        if arg_val := request.query_params.get(list_field):
            filter_list = arg_val.split('|')
            if list_field in ['id', 'batch_id']:
                filter_list = [int(x) for x in filter_list]
            field_parts = list_field.split('.')
            sub_fields = field_parts[1:]
            db_field = field_parts[0]
            if sub_fields:
                db_field += ' ->> ?'
            where_clauses.append(f'{db_field} IN ({",".join(["?"] * len(filter_list))})')
            params.extend(sub_fields)
            params.extend(filter_list)
    with DbContext() as (conn, cur):
        result = cur.execute(f"""
            SELECT * FROM {table}
            {"WHERE " + " AND ".join(where_clauses) if where_clauses else ""}
            ORDER BY {sort_field} {direction}
            LIMIT ? OFFSET ?
        """, (*params, limit, offset))
        return [
            {
                **dict(row),
                'record': json.loads(row['record']),
            }
            for row in result.fetchall()
        ]