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


# --- The website's history files (owner asked: the public sees the last 7 days; older history needs the passphrase).
# One key is derived once per export with PBKDF2-SHA256 from the passphrase and a fixed salt, so the browser derives
# it once too (web/js/lock.js) and opens every file with it. Each file: b"GSO1" + 12-byte nonce + AES-256-GCM
# ciphertext (with its tag), so a wrong key or a damaged file is detected, never shown as data.
import base64
import hashlib

SITE_MAGIC = b"GSO1"
SITE_ITERATIONS = 600_000
SITE_SALT = hashlib.sha256(b"gso-data-archive site lock v1").digest()[:16]
CHECK_TEXT = b"gso-data-archive unlocked"
PUBLIC_DAYS = 7  # web/js/lock.js shows the same number


def site_key(secret: str) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), SITE_SALT, SITE_ITERATIONS, dklen=32)


def seal_bytes(key: bytes, data: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    return SITE_MAGIC + nonce + AESGCM(key).encrypt(nonce, data, None)


def unseal_bytes(key: bytes, blob: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not blob.startswith(SITE_MAGIC):
        raise ValueError("not a locked file")
    return AESGCM(key).decrypt(blob[4:16], blob[16:], None)


def lock_info(key: bytes, public_from: str, history_from: str | None) -> dict:
    """What the browser needs to ask for the passphrase and check it (published in meta.json)."""
    b64 = lambda b: base64.b64encode(b).decode("ascii")  # noqa: E731
    return {"public_days": PUBLIC_DAYS, "public_from": public_from, "history_from": history_from,
            "salt": b64(SITE_SALT), "iterations": SITE_ITERATIONS, "check": b64(seal_bytes(key, CHECK_TEXT))}
