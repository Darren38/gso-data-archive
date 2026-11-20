"""Locking the archive copies that leave the Actions cache (the website copy and the daily backups).

When the repository secret ARCHIVE_PASSPHRASE is set, both copies are encrypted with it before they are published, so
only the owner can open them; without it they stay as before. OpenSSL's AES-256 with a PBKDF2 key is used, so a copy
can be opened anywhere without this project:

    openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -in FILE.enc -out FILE      (asks for the passphrase)

The passphrase reaches OpenSSL through the environment, never the command line, so it can't show up in a log.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

PASS_ENV = "ARCHIVE_PASSPHRASE"
SUFFIX = ".enc"
_CIPHER = ["-aes-256-cbc", "-pbkdf2", "-iter", "600000"]


def passphrase() -> str | None:
    """The passphrase, or None when the archive copies are published unlocked."""
    return os.environ.get(PASS_ENV) or None


def _openssl(args: list[str], src: Path, dst: Path) -> None:
    if not passphrase():
        raise RuntimeError(f"{PASS_ENV} is not set")
    res = subprocess.run(["openssl", "enc", *args, *_CIPHER, "-pass", f"env:{PASS_ENV}", "-in", str(src), "-out", str(dst)],
                         capture_output=True, text=True, check=False)
    if res.returncode != 0:
        dst.unlink(missing_ok=True)
        raise RuntimeError(f"openssl failed: {res.stderr.strip()[:200]}")


def seal(src: Path, dst: Path) -> None:
    """Encrypt `src` into `dst`."""
    _openssl(["-salt"], src, dst)


def unseal(src: Path, dst: Path) -> None:
    """Decrypt `src` into `dst`; raises for a wrong passphrase or a damaged file."""
    _openssl(["-d"], src, dst)
