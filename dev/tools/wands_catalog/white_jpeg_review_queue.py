"""Prioritize measured low-risk pairs without changing any acceptance checks."""
import heapq
from pathlib import Path
import sqlite3
import time


class ReviewQueue:
    def __init__(self, audit, rows, identity, refresh_seconds=10):
        self.path = Path(audit) / 'review-priority/features.sqlite3'
        self.remaining = {row['file']: row for row in rows}
        self.fallback = iter(tuple(self.remaining))
        self.heap = []
        self.identity = identity
        self.cursor = 0
        self.refreshed = None
        self.refresh_seconds = refresh_seconds

    def __iter__(self):
        return self

    def refresh(self):
        now = time.monotonic()
        if self.refreshed is not None and now - self.refreshed < self.refresh_seconds:
            return
        self.refreshed = now
        if not self.path.is_file():
            return
        with sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True, timeout=5) as db:
            measured = db.execute('SELECT rowid,file,source_sha256,output_sha256,identity,screen,region_count FROM features WHERE rowid>? ORDER BY rowid', (self.cursor,)).fetchall()
        for number, file, source_hash, output_hash, identity, screen, regions in measured:
            self.cursor = number
            row = self.remaining.get(file)
            if row is None:
                continue
            if (identity != self.identity or source_hash != row['source_sha256'] or output_hash != row.get('output_sha256')):
                raise ValueError('Review priority inputs changed')
            heapq.heappush(self.heap, (-1 if screen else regions, file))

    def __next__(self):
        self.refresh()
        while self.heap:
            _, file = heapq.heappop(self.heap)
            row = self.remaining.pop(file, None)
            if row is not None:
                return row
        for file in self.fallback:
            row = self.remaining.pop(file, None)
            if row is not None:
                return row
        raise StopIteration
