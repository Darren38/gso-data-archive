"""Raw source response archive (gzip files, content-addressed by SHA-256).

Files live under RAW_STORE_DIR, which should be synced to object storage
(see docs/BACKUP_RESTORE.md). The database only stores metadata and the path.
"""

from __future__ import annotations

import gzip
import hashlib
from datetime import datetime
from pathlib import Path


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class RawStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def write(self, adapter: str, fetched_at: datetime, content: bytes, digest: str) -> str:
        rel = Path(adapter) / fetched_at.strftime("%Y/%m/%d") / f"{fetched_at.strftime('%H%M%S')}_{digest[:16]}.json.gz"
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with gzip.open(tmp, "wb") as fh:
            fh.write(content)
        tmp.replace(path)  # atomic: never leaves a half-written snapshot
        return rel.as_posix()

    def read(self, rel_path: str) -> bytes:
        with gzip.open(self.root / rel_path, "rb") as fh:
            return fh.read()
