# Tracks expense and writes them to the sqlite table

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.db.utils import DbContext


@dataclass
class ExpenseEntry:
    phase: str
    toc_queue_id: int
    cost: int
    duration: int
    batch_id: int | None
    record: dict[str, Any]

    def to_sql(self) -> tuple[str, tuple]:
        """Return SQL statement and parameters for inserting this expense."""
        return (
            """
                INSERT INTO expenses (toc_queue_id, batch_id, phase, cost, duration, record)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                self.toc_queue_id,
                self.batch_id,
                self.phase,
                self.cost,
                self.duration,
                json.dumps(self.record)
            )
        )


@dataclass
class DbExpenseEntry(ExpenseEntry):
    id: int
    created: datetime

    @staticmethod
    def from_db_row(row: dict) -> 'DbExpenseEntry':
        """Create a DbExpenseEntry instance from a database row."""
        return DbExpenseEntry(
            id=row['id'],
            created=row['created'],
            toc_queue_id=row['toc_queue_id'],
            batch_id=row['batch_id'],
            phase=row['phase'],
            cost=row['cost'],
            duration=row['duration'],
            record=json.loads(row['record'])
        )


class ExpenseTracker:
    def __init__(self):
        pass

    def add_expense(self, entry: ExpenseEntry) -> int | None:
        """Add an expense entry to the database and return the expense ID."""
        with DbContext() as (conn, cur):
            sql, params = entry.to_sql()
            cur.execute(sql, params)
            conn.commit()
            return cur.lastrowid

    @staticmethod
    def get_expenses_by_batch(batch_id: int) -> list[DbExpenseEntry]:
        """Get all expenses for a specific batch."""
        with DbContext() as (conn, cur):
            cur.execute("""
                SELECT id, created, toc_queue_id, batch_id, phase, cost, duration, record
                FROM expenses
                WHERE batch_id = ?
                ORDER BY created ASC
            """, (batch_id,))
            
            return [DbExpenseEntry.from_db_row(row) for row in cur.fetchall()]

    @staticmethod
    def get_expenses_by_toc_queue_ids(toc_queue_ids: list[int]) -> list[DbExpenseEntry]:
        """Get all expenses for a list of toc_queue item IDs."""
        if not toc_queue_ids:
            return []
        # Ensure all IDs are integers to prevent SQL injection
        placeholders = ','.join('?' for _ in toc_queue_ids)
        query = f"""
            SELECT id, created, toc_queue_id, batch_id, phase, cost, duration, record
            FROM expenses
            WHERE toc_queue_id IN ({placeholders})
            ORDER BY created ASC
        """
        with DbContext() as (_, cur):
            cur.execute(query, toc_queue_ids)
            return [DbExpenseEntry.from_db_row(row) for row in cur.fetchall()]

    @staticmethod
    def get_expense_by_id(expense_id: int) -> DbExpenseEntry | None:
        """Get a single expense by its ID."""
        with DbContext() as (conn, cur):
            cur.execute("""
                SELECT id, created, toc_queue_id, batch_id, phase, cost, duration, record
                FROM expenses
                WHERE id = ?
            """, (expense_id,))
            
            row = cur.fetchone()
            return DbExpenseEntry.from_db_row(row) if row else None

    @staticmethod
    def get_total_cost_by_batch(batch_id: int) -> int:
        """Get the total cost for a batch in micropennies."""
        with DbContext() as (conn, cur):
            cur.execute("""
                SELECT COALESCE(SUM(cost), 0) as total_cost
                FROM expenses
                WHERE batch_id = ?
            """, (batch_id,))
            return cur.fetchone()[0]
