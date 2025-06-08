from itertools import cycle, islice
import sys
from app.db.utils import DbContext, throttle
from tocky.batches import DbBatch

MAX_RUNNING_JOBS = 10
THROTTLE_PERIOD = 5

          
@throttle(THROTTLE_PERIOD, lock=True)
async def process_batches():
    with DbContext() as (conn, cur):
        # Fetch number of running jobs
        cur.execute("SELECT COUNT(*) FROM toc_queue WHERE state NOT IN ('Done', 'Errored', 'To Review')")
        running_jobs_count = cur.fetchone()[0]
        budget = MAX_RUNNING_JOBS - running_jobs_count
        print(f"[WORKER] Running jobs: {running_jobs_count}, Budget for new jobs: {budget}", file=sys.stderr, flush=True)

        # Fetch pending batches updated by least recently
        # updated first.
        cur.execute("""
            SELECT * FROM batches
            WHERE state IN ('Pending', 'Processing')
            ORDER BY updated ASC
            LIMIT ?
        """, (budget,))
        batches = list(map(DbBatch.from_db_row, cur.fetchall()))

        print(f"[WORKER] {len(batches)} batches to process", file=sys.stderr, flush=True)

        if budget <= 0:
            print(f"[WORKER] No budget for new jobs, exiting.", file=sys.stderr, flush=True)


            if batches:
                t = process_batches()
                return

        for batch in islice(cycle(batches), budget):
            await batch.start_next_job()
