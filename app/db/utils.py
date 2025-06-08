import asyncio
from collections.abc import Callable
import json
import sqlite3
from pathlib import Path
import time
from typing import Any, Awaitable, Sequence, TypeVar, cast
from functools import wraps

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

T = TypeVar('T')

def throttle(period: int = 1, lock: bool = False):
    """
    Throttle function to prevent too frequent calls.
    Stores the last call time in the database.

    :param period: Time in seconds to wait before allowing the next call.
    :param lock: If True, will use a lock to ensure only one call can be made at a time.
    """

    def decorator(func):
        @wraps(func)
        async def wrapper():
            key = f"{func.__module__}.{func.__name__}_throttle"
            
            with DbContext() as (conn, cur):
                is_locked = False
                if lock:
                    lock_key = f"{key}_lock"
                    cur.execute("SELECT value FROM tocky_internals WHERE key = ?", (lock_key,))
                    row = cur.fetchone()
                    is_locked = json.loads(row['value']) if row else False

                cur.execute("SELECT value FROM tocky_internals WHERE key = ?", (key,))
                row = cur.fetchone()
                if row:
                    last_call_time = cast(float, row['value'])
                else:
                    last_call_time = None

                now = time.time()
                time_has_passed = not last_call_time or (now - last_call_time) >= period
                if not is_locked and time_has_passed:
                    print(f"Calling {func.__name__} at {now}, last call was at {last_call_time}")
                    last_call_time = now
                    cur.execute("""
                        INSERT OR REPLACE INTO tocky_internals (key, value)
                        VALUES (?, ?)
                    """, (key, json.dumps(last_call_time)))
                    conn.commit()

                    if lock:
                        # Acquire lock
                        cur.execute("""
                            INSERT OR REPLACE INTO tocky_internals (key, value)
                            VALUES (?, ?)
                        """, (lock_key, json.dumps(True)))
                        conn.commit()
                    try:
                        await func()
                    finally:
                        if lock:
                            # Release lock
                            cur.execute("""
                                INSERT OR REPLACE INTO tocky_internals (key, value)
                                VALUES (?, ?)
                            """, (lock_key, json.dumps(False)))
                            conn.commit()
                    return
                else:
                    next_key = f"{key}_next"
                    cur.execute("""
                        SELECT value FROM tocky_internals
                        WHERE key = ?
                    """, (next_key,))
                    row = cur.fetchone()
                    next_call_time = cast(float, row['value']) if row else None
                    if next_call_time and next_call_time > now:
                        # Already queued up, so do nothing
                        print(f"Already throttled {func.__name__}, next call at {next_call_time}")
                    else:
                        # Update the next call time
                        cur.execute("""
                            INSERT OR REPLACE INTO tocky_internals (key, value)
                            VALUES (?, ?)
                        """, (next_key, json.dumps(now + period)))
                        conn.commit()
                        sleep_time = period - (now - last_call_time) if last_call_time else period
                        print(f"Throttling {func.__name__}, next call at {now + sleep_time}")
                        await asyncio.sleep(sleep_time)
                        await wrapper()
                        return

        return wrapper

    return decorator
