import asyncio
from collections.abc import Callable
import json
import os
import sqlite3
from pathlib import Path
import sys
import time
from typing import Sequence, TypeVar, cast
from functools import wraps
from psutil import Process

from fastapi import Request
from fastapi.responses import JSONResponse

from tocky.env import get_env

env = get_env()


class DbContext:
    def __init__(self, timeout: float = 5.0):
        self.conn = sqlite3.connect(env.TOCKY_QUEUE_DB_PATH, timeout=timeout)
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
                    if last_call_time:
                        print(f"[THROTTLE:{func.__name__}] Calling at {now}, last call was at {(now - last_call_time):.2f}s ago.", file=sys.stderr, flush=True)
                    else:
                        print(f"[THROTTLE:{func.__name__}] Calling at {now}, last call was never.", file=sys.stderr, flush=True)
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
                        print(f"[THROTTLE:{func.__name__}] Skipping, next call at {next_call_time:.2f}", file=sys.stderr, flush=True)
                    else:
                        # Update the next call time
                        cur.execute("""
                            INSERT OR REPLACE INTO tocky_internals (key, value)
                            VALUES (?, ?)
                        """, (next_key, json.dumps(now + period)))
                        conn.commit()
                        sleep_time = period - (now - last_call_time) if last_call_time else period
                        print(f"[THROTTLE:{func.__name__}] Throttling, next call at {now + sleep_time:.2f}", file=sys.stderr, flush=True)
                        await asyncio.sleep(sleep_time)
                        await wrapper()
                        return

        return wrapper

    return decorator


def is_process_running(pid: int, create_time: float | None = None) -> bool:
    """Check if a process with the given PID, and optionally given create_time, is running."""
    try:
        os.kill(pid, 0)
        # It's running, now check if the create time matches
        if create_time is not None:
            return Process(pid).create_time() == create_time
        else:
            return True
    except OSError:
        return False


def rate_limit(
    calls: int,
    period: int,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Rate limit a function to a certain number of calls per period.
    
    :param calls: Number of allowed calls in the period.
    :param period: Time in seconds for the rate limit.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        pid = os.getpid()
        id_prefix = f"{pid}#{Process(pid).create_time()}"
        key = f"{func.__module__}.{func.__name__}_rate_limit"

        # Remove queued calls from not running processes
        with DbContext() as (conn, cur):
            cur.execute("SELECT value FROM tocky_internals WHERE key = ?", (key,))
            row = cur.fetchone()
            if row:
                queue, last_calls = cast(tuple[list[str], list[float]], json.loads(row['value']))
            else:
                queue: list[str] = []
                last_calls: list[float] = []
            
            # Remove calls from no longer running processes
            # Tuple of (pid, create_time) is used to identify the process
            queue_processes: set[tuple[int, float]] = {
                # Get the PID and create time, drop the request id
                (int(pid), float(pid_create_time))
                for pid, pid_create_time, req_id in (
                    tuple(c.split('#'))
                    for c in queue
                )
            }
            running_processes = {
                f"{pid}#{create_time}"
                for (pid, create_time) in queue_processes
                if is_process_running(pid, create_time)
            }
            new_queue = [c for c in queue if c.rsplit('#', 1)[0] in running_processes]

            if queue != new_queue:
                print(f"[RATE-LIMIT:{func.__name__}] Cleaning up queue, removed {len(queue) - len(new_queue)} calls from dead processes", file=sys.stderr, flush=True)

                # Store the current process ID and the key for the rate limit
                cur.execute("""
                    INSERT OR REPLACE INTO tocky_internals (key, value)
                    VALUES (?, ?)
                """, (key, json.dumps((new_queue, last_calls))))
                conn.commit()

        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            # GUID for the call, to ensure uniqueness
            request_time = time.time()
            call_id = f"{id_prefix}#{request_time}"
            while True:
                # Use larger timeout to avoid lock contention
                with DbContext(timeout=30) as (conn, cur):
                    cur.execute("BEGIN IMMEDIATE")
                    cur.execute("SELECT value FROM tocky_internals WHERE key = ?", (key,))
                    row = cur.fetchone()
                    if row:
                        queue, last_calls = cast(tuple[list[str], list[float]], json.loads(row['value']))
                    else:
                        queue: list[str] = []
                        last_calls: list[float] = []

                    now = time.time()

                    # Update the state
                    if call_id not in queue:
                        queue.append(call_id)
                    last_calls = [t for t in last_calls if now - t < period]
                    available_calls = max(0, calls - len(last_calls))

                    if call_id in queue[:available_calls]:
                        # Remove the call from the queue
                        queue = [cid for cid in queue if cid != call_id]
                        last_calls.append(now)

                        # Commit state + release the lock
                        cur.execute("""
                            INSERT OR REPLACE INTO tocky_internals (key, value)
                            VALUES (?, ?)
                        """, (key, json.dumps((queue, last_calls))))
                        conn.commit()

                        print(f"[RATE-LIMIT:{func.__name__}] Calling, after {now - request_time:.2f}s", file=sys.stderr, flush=True)
                        return func(*args, **kwargs)
                    else:
                        # If we have reached the limit, wait for the next available slot
                        wait_time = period - (now - last_calls[0]) if last_calls else period
                        print(f"[RATE-LIMIT:{func.__name__}] Rate limit exceeded, waiting {wait_time:.2f} seconds")

                        cur.execute("""
                            INSERT OR REPLACE INTO tocky_internals (key, value)
                            VALUES (?, ?)
                        """, (key, json.dumps((queue, last_calls))))
                        # Release the lock
                        conn.commit()

                        time.sleep(wait_time)

        return wrapper 
    return decorator

def clear_dead_jobs():
    """
    Clear jobs that are in the 'Processing' state but have not been updated for a long time.
    This is useful to clean up jobs that may have been left in a processing state due to crashes or other issues.
    """
    with DbContext() as (conn, cur):
        cur.execute("""
            SELECT id, process_id_str FROM toc_queue
            WHERE state IN ('To Extract', 'Extracting', 'To Detect', 'Detecting')
        """) 
        rows = cur.fetchall()
        for row in rows:
            job_id = row['id']
            process_id_str = row['process_id_str']
            (pid, create_time) = process_id_str.split('#')
            if not pid or not is_process_running(int(pid), float(create_time)):
                print(f"[DB-CLEANUP] Job {job_id} is dead, clearing it", file=sys.stderr, flush=True)
                # Set its state to 'Errored'
                cur.execute("""
                    UPDATE toc_queue
                    SET state = 'Errored'
                    WHERE id = ?
                """, (job_id,))
                conn.commit()