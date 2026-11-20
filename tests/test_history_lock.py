"""Locked history (the owner's choice): with ARCHIVE_PASSPHRASE set, the public files hold only the newest 7 days and
the full history is published locked, opened in the browser by web/js/lock.js."""

import base64
import json
import shutil
import subprocess
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pytest

from gso_archive.export_static import export_site
from gso_archive.sealing import PUBLIC_DAYS, site_key, unseal_bytes
from gso_archive.timeutil import MYT

from .test_archive_sync import two_archives  # noqa: F401 - fixture

SCRIPT = Path(__file__).parent / "frontend" / "check_lock.mjs"
PASS = "a made-up test passphrase"  # never the owner's real one


def _day(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(MYT).date()


@pytest.fixture
def locked_site(two_archives, settings, tmp_path, monkeypatch):  # noqa: F811
    a, _, a_url, _ = two_archives
    monkeypatch.setenv("ARCHIVE_PASSPHRASE", PASS)
    site = tmp_path / "site"
    export_site(a, replace(settings, database_url=a_url), site)
    return site / "data"


def test_public_files_hold_only_the_newest_days(locked_site):
    data = locked_site
    lock = json.loads((data / "meta.json").read_text())["lock"]
    assert lock["public_days"] == PUBLIC_DAYS and lock["iterations"] >= 600_000
    pf = date.fromisoformat(lock["public_from"])
    key = site_key(PASS)
    assert unseal_bytes(key, base64.b64decode(lock["check"])) == b"gso-data-archive unlocked"
    with pytest.raises(Exception):
        unseal_bytes(site_key("wrong"), base64.b64decode(lock["check"]))
    locked = list(data.rglob("*.json.enc"))
    assert locked, "nothing was locked"
    for enc in locked:
        json.loads(unseal_bytes(key, enc.read_bytes()))  # every locked file opens with the key
        plain = enc.with_suffix("")
        if plain.exists():
            pub = json.loads(plain.read_text())
            assert all(_day(p[0]) >= pf for p in pub.get("points") or []), plain
            assert all(r["date"] >= lock["public_from"] for r in pub.get("rows") or [] if "date" in r), plain
            assert all(d >= lock["public_from"] for d in pub.get("days") or []), plain
    assert not list(data.rglob("exports/**/*.csv")), "monthly CSVs must not be published while history is locked"
    assert not (data / "archive.sqlite3.gz").exists()


def test_old_readings_only_in_locked_files(two_archives, settings, tmp_path, monkeypatch):  # noqa: F811
    """Readings older than the public week are in the locked copy and in no public file."""
    a, _, a_url, _ = two_archives
    monkeypatch.setenv("ARCHIVE_PASSPHRASE", PASS)
    monkeypatch.setattr("gso_archive.export_static.PUBLIC_DAYS", 0)  # the public window starts after the sample day: every reading is "old"
    data = tmp_path / "site" / "data"
    export_site(a, replace(settings, database_url=a_url), data.parent)
    pf = json.loads((data / "meta.json").read_text())["lock"]["public_from"]
    key = site_key(PASS)
    old_locked = old_public = 0
    for enc in data.glob("points/*/*.json.enc"):
        old_locked += sum(1 for p in json.loads(unseal_bytes(key, enc.read_bytes()))["points"] if str(_day(p[0])) < pf)
        plain = enc.with_suffix("")
        if plain.exists():
            old_public += sum(1 for p in json.loads(plain.read_text())["points"] if str(_day(p[0])) < pf)
    assert old_locked > 0 and old_public == 0


def test_unlocked_export_unchanged(two_archives, settings, tmp_path, monkeypatch):  # noqa: F811
    a, _, a_url, _ = two_archives
    monkeypatch.delenv("ARCHIVE_PASSPHRASE", raising=False)
    data = tmp_path / "site" / "data"
    export_site(a, replace(settings, database_url=a_url), data.parent)
    assert "lock" not in json.loads((data / "meta.json").read_text())
    assert not list(data.rglob("*.enc")) and list(data.rglob("exports/**/*.csv"))


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_browser_opens_what_python_locked(locked_site):
    r = subprocess.run([shutil.which("node"), str(SCRIPT), str(locked_site), PASS], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr or r.stdout


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_unlock_in_the_browser(locked_site):
    """Locked: only short ranges and the public days; a wrong password is refused; the right one opens the long
    ranges; Lock closes them again. At 320 and 1280 px, no sideways scrolling."""
    from .test_archive_sync import serve

    httpd, base = serve(locked_site.parent)
    try:
        r = subprocess.run([shutil.which("node"), str(Path(__file__).parent / "frontend" / "check_lock_ui.cjs"), base, PASS],
                           capture_output=True, text=True, timeout=240, cwd=Path(__file__).parent.parent)
    finally:
        httpd.shutdown()
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr or r.stdout
