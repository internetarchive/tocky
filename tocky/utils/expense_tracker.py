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
    def from_db_row(row: tuple) -> 'DbExpenseEntry':
        """Create a DbExpenseEntry instance from a database row."""
        return DbExpenseEntry(
            id=row[0],
            created=row[1],
            toc_queue_id=row[2],
            batch_id=row[3],
            phase=row[4],
            cost=row[5],
            duration=row[6],
            record=json.loads(row[7])
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

    def get_expenses_by_batch(self, batch_id: int) -> list[DbExpenseEntry]:
        """Get all expenses for a specific batch."""
        with DbContext() as (conn, cur):
            cur.execute("""
                SELECT id, created, toc_queue_id, batch_id, phase, cost, duration, record
                FROM expenses
                WHERE batch_id = ?
                ORDER BY created DESC
            """, (batch_id,))
            
            return [DbExpenseEntry.from_db_row(row) for row in cur.fetchall()]

    def get_expenses_by_toc_queue(self, toc_queue_id: int) -> list[DbExpenseEntry]:
        """Get all expenses for a specific toc_queue item."""
        with DbContext() as (conn, cur):
            cur.execute("""
                SELECT id, created, toc_queue_id, batch_id, phase, cost, duration, record
                FROM expenses
                WHERE toc_queue_id = ?
                ORDER BY created DESC
            """, (toc_queue_id,))
            
            return [DbExpenseEntry.from_db_row(row) for row in cur.fetchall()]

    def get_expense_by_id(self, expense_id: int) -> DbExpenseEntry | None:
        """Get a single expense by its ID."""
        with DbContext() as (conn, cur):
            cur.execute("""
                SELECT id, created, toc_queue_id, batch_id, phase, cost, duration, record
                FROM expenses
                WHERE id = ?
            """, (expense_id,))
            
            row = cur.fetchone()
            return DbExpenseEntry.from_db_row(row) if row else None

    def get_total_cost_by_batch(self, batch_id: int) -> int:
        """Get the total cost for a batch in micropennies."""
        with DbContext() as (conn, cur):
            cur.execute("""
                SELECT COALESCE(SUM(cost), 0) as total_cost
                FROM expenses
                WHERE batch_id = ?
            """, (batch_id,))
            return cur.fetchone()[0]
