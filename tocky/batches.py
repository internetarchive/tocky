from dataclasses import dataclass, field
from datetime import datetime
import json
import sys
from typing import Literal

import httpx
import requests

from app.db.utils import DbContext
from tocky.env import get_env

env = get_env()

BatchState = Literal[
    "Pending",     # the batch jobs are queued and waiting to be processed.
    "Processing",  # one of the batch jobs is currently being processed.
    "Completed",   # all batch jobs have been processed successfully.
    "Failed",      # one or more batch jobs have failed during processing.
    "Cancelled",   # the batch processing has been cancelled before completion.
    "Paused",      # the batch processing has been temporarily paused.
]

@dataclass
class Batch:
    creator: str | None
    name: str | None
    state: BatchState
    offset: int
    limit: int
    query: str
    toc_filter: str
    detector: dict
    extractor: dict
    skip_processed_books: bool

    @property
    def full_query(self) -> str:
        return f'({self.query}) AND {self.toc_filter}'

    @staticmethod
    def from_submit_input(input_dict: dict):
        return Batch(
            creator=input_dict.get('creator'),
            name=input_dict['batch'].get('name'),
            state='Pending',
            offset=0,
            limit=0,  # Computed later
            query=input_dict['batch']['query'],
            toc_filter=input_dict['batch']['toc_filter'],
            detector=input_dict['detector'],
            extractor=input_dict['extractor'],
            skip_processed_books=input_dict['batch']['skip_processed_books']
        )
    
    def to_sql(self) -> tuple[str, tuple]:
        return (
            """
                INSERT INTO batches (creator, name, record)
                VALUES (?, ?, ?)
            """,
            (
                self.creator,
                self.name,
                json.dumps(self.__dict__),
            )
        )

    def get_total(self) -> int:
        """
        Calculate the total number of items in a batch based on its record.
        The record is expected to be a JSON string with an 'offset' field.
        """
        resp = requests.get('https://archive.org/advancedsearch.php', params={
            'q': self.full_query,
            'fl': 'identifier',
            'rows': '0',  # We only need the total count
            'output': 'json',
        })
        resp.raise_for_status()
        total = resp.json()['response']['numFound']
        return total

@dataclass
class DbBatch(Batch):
    id: int
    created: datetime
    updated: datetime
    skipped: int = 0

    @staticmethod
    def from_db_row(row: dict) -> 'DbBatch':
        """
        Create a DbBatch instance from a database row.
        The row is expected to have keys: id, created, updated, record.
        """
        batch = json.loads(row['record'])
        return DbBatch(
            id=row['id'],
            created=row['created'],
            updated=row['updated'],
            creator=batch['creator'],
            name=batch['name'],
            state=batch['state'],
            offset=batch['offset'],
            limit=batch['limit'],
            query=batch['query'],
            toc_filter=batch['toc_filter'],
            detector=batch['detector'],
            extractor=batch['extractor'],
            # This field was added later, so if unspecified assume false
            skip_processed_books=batch.get('skip_processed_books', False),
        )

    async def start_next_job(self) -> None:
        print(f"[TOCKY-BATCH] Batch #{self.id}: Start next job", file=sys.stderr, flush=True)
        with DbContext() as (conn, cur):
            if self.offset == 0:
                # Set it to Processing
                cur.execute("""
                    UPDATE batches
                    SET state = 'Processing', updated = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (self.id,))
                conn.commit()
            elif self.offset >= self.limit:
                # If offset is greater than or equal to limit, mark as completed
                cur.execute("""
                    UPDATE batches
                    SET state = 'Completed', updated = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (self.id,))
                conn.commit()
                print(f"[TOCKY-BATCH] Batch #{self.id}: Offset complete.", file=sys.stderr, flush=True)
                return

            async with httpx.AsyncClient() as client:
                resp = await client.get('https://archive.org/advancedsearch.php', params={
                    'q': self.full_query,
                    'fl': 'identifier,openlibrary_edition',
                    'rows': 1,
                    'page': self.offset + 1,
                    # Need to sort by something to ensure consistent results; might want
                    # to make this configurable in the future.
                    'sort': '-week',
                    'output': 'json',
                })
                resp.raise_for_status()
                ia_record = resp.json()['response']['docs']

                if not ia_record:
                    cur.execute("UPDATE batches SET state = 'Completed' WHERE id = ?", (self.id,))
                    conn.commit()
                    print(f"[TOCKY-BATCH] Batch #{self.id}: no more records, marking as completed.", file=sys.stderr, flush=True)
                    return

                ia_record = ia_record[0]

                skip = False
                if self.skip_processed_books:
                    cur.execute("""
                        SELECT COUNT(*) FROM toc_queue
                        WHERE record->>'$.ocaid' = ? AND state != 'Errored'
                    """, (ia_record['identifier'],))
                    skip = cur.fetchone()[0] > 0


                if skip:
                    print(f"[TOCKY-BATCH] Batch #{self.id}: Skipping already processed book {ia_record['identifier']}", file=sys.stderr, flush=True)
                    self.skipped += 1
                    cur.execute("""
                        UPDATE batches
                        SET record = json_set(record, '$.skipped', ?), updated = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (self.skipped, self.id))
                    conn.commit()
                else:
                    print(f"[TOCKY-BATCH] Batch #{self.id}: Processing {ia_record['identifier']} at offset {self.offset}\n{resp.url}", file=sys.stderr, flush=True)

                    await client.post(
                        f'{env.TOCKY_INTERNAL_URL}/submit',
                        timeout=5,
                        headers={
                            'X-API-KEY': env.TOCKY_SERVER_KEY,
                            'Content-Type': 'application/json',
                        },
                        params={
                            'background': 'true',
                        },
                        json={
                            'creator': self.creator,
                            'batch_id': self.id,
                            'input_book': {
                                'ia_id': ia_record['identifier'],
                            },
                            'detector': self.detector,
                            'extractor': self.extractor,
                        }
                    )

            # Update batch offset
            self.offset += 1
            cur.execute("""
                UPDATE batches
                SET record = json_set(record, '$.offset', ?), updated = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (self.offset, self.id))
            conn.commit()

            if skip:
                return await self.start_next_job()
