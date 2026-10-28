"""Single-instance lock so two collectors never write concurrently.

PostgreSQL: session advisory lock (works across machines sharing the DB).
SQLite: an exclusive file lock next to the database file.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

LOCK_ID = 0x650_A2C4  # arbitrary constant for pg_try_advisory_lock


class LockBusy(Exception):
    pass


@contextlib.contextmanager
def collector_lock(engine: Engine):
    if engine.dialect.name == "postgresql":
        with engine.connect() as conn:
            got = conn.execute(text("SELECT pg_try_advisory_lock(:id)"), {"id": LOCK_ID}).scalar()
            if not got:
                raise LockBusy("another collector holds the PostgreSQL advisory lock")
            try:
                yield
            finally:
                conn.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": LOCK_ID})
                conn.commit()
        return

    import fcntl

    db_path = engine.url.database or ":memory:"
    lock_path = Path(db_path + ".collector.lock") if db_path != ":memory:" else Path(os.devnull)
    if db_path == ":memory:":
        yield
        return
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LockBusy(f"another collector holds {lock_path}") from None
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
