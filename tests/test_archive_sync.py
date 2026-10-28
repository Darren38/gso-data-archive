"""GitHub-only mode: carrying the archive between runs, merging copies, and the site check-up."""

import functools
import gzip
import http.server
import json
import threading
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import func, select

from gso_archive import db
from gso_archive.adapters import get_adapter
from gso_archive.archive_sync import merge_archive, seed_from_live, write_snapshot
from gso_archive.collector import collect_one
from gso_archive.db import make_engine
from gso_archive.export_static import export_site
from gso_archive.health import check_site
from gso_archive.http import GsoClient
from gso_archive.migrations import migrate

from .conftest import fixture_bytes

GEN = "SystemData/CurrentGen.aspx/GetChartDataSource"


def sqlite_archive(tmp_path, name):
    url = f"sqlite:///{tmp_path / name}"
    eng = make_engine(url)
    migrate(eng)
    return url, eng


def collect(settings, eng, url, fixtures, day):
    s = replace(settings, database_url=url)
    queue = list(fixtures)

    def handler(req):
        if req.method == "GET":
            return httpx.Response(200, text="ok")
        body = json.loads(req.content)
        rows = json.loads(json.loads(fixture_bytes(queue.pop(0) if len(queue) > 1 else queue[0]))["d"])
        d = datetime.strptime(body["Fromdate"], "%d/%m/%Y").date().isoformat()
        for r in rows:
            r["DT"] = d + r["DT"][10:]
        return httpx.Response(200, json={"d": json.dumps(rows)})

    with GsoClient(s, transport=httpx.MockTransport(handler)) as c:
        for f in fixtures:
            collect_one(eng, c, s, get_adapter("generation_mix"), day)


def counts(eng):
    with eng.connect() as c:
        return {t.name: c.execute(select(func.count()).select_from(t)).scalar()
                for t in (db.observations, db.observation_revisions, db.collection_runs, db.series)}


@pytest.fixture
def two_archives(settings, tmp_path):
    if not settings.database_url.startswith("sqlite"):
        pytest.skip("GitHub-only mode uses SQLite")
    a_url, a = sqlite_archive(tmp_path, "a.sqlite3")
    b_url, b = sqlite_archive(tmp_path, "b.sqlite3")
    # A: day 27 collected twice with a revision; B: day 28 (A never saw it)
    collect(settings, a, a_url, ["currentgen_2026-10-27.json", "currentgen_revised.json"], date(2026, 10, 27))
    collect(settings, b, b_url, ["currentgen_2026-10-27.json"], date(2026, 10, 28))
    return a, b, a_url, b_url


def test_merge_keeps_the_union(two_archives):
    a, b, *_ = two_archives
    stats = merge_archive(a, b)
    assert stats["observations"] == 288 and stats["revisions"] == 289
    got = counts(b)
    assert got["observations"] == 576 and got["observation_revisions"] == 577 and got["collection_runs"] == 3
    with b.connect() as c:
        rev = c.execute(select(db.observations).where(db.observations.c.value == 9999.0)).one()
    assert rev.revision_count == 2  # history of the revised reading came along


def test_merge_is_repeatable_and_one_way_safe(two_archives):
    a, b, *_ = two_archives
    merge_archive(a, b)
    before = counts(b)
    assert "skipped" in merge_archive(a, b)  # nothing new
    assert counts(b) == before
    merge_archive(b, a)  # the other direction converges to the same archive
    assert counts(a) == before


def test_merge_newer_change_wins(settings, tmp_path):
    if not settings.database_url.startswith("sqlite"):
        pytest.skip("SQLite only")
    a_url, a = sqlite_archive(tmp_path, "a.sqlite3")
    b_url, b = sqlite_archive(tmp_path, "b.sqlite3")
    collect(settings, b, b_url, ["currentgen_2026-10-27.json"], date(2026, 10, 27))
    collect(settings, a, a_url, ["currentgen_revised.json"], date(2026, 10, 27))  # A saw the later, revised value
    merge_archive(a, b)
    with b.connect() as c:
        assert c.execute(select(func.max(db.observations.c.value))).scalar() == 9999.0


def serve(directory):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}/"


def test_seed_from_live_site(two_archives, settings, tmp_path):
    a, b, a_url, b_url = two_archives
    site = tmp_path / "site"
    out = export_site(a, replace(settings, database_url=a_url), site)
    assert out["archive_bytes"] and (site / "data" / "archive.sqlite3.gz").exists()
    httpd, base = serve(site)
    try:
        fresh_url = f"sqlite:///{tmp_path / 'fresh' / 'archive.sqlite3'}"
        r1 = seed_from_live(fresh_url, base)
        assert r1["seeded"] and "copied" in r1["how"]
        assert counts(make_engine(fresh_url)) == counts(a)
        r2 = seed_from_live(b_url, base)  # an existing archive is merged, not replaced
        assert r2["seeded"] and r2["how"] == "merged"
        assert counts(b)["observations"] == 576
    finally:
        httpd.shutdown()


def test_seed_without_live_copy_keeps_local(settings, tmp_path):
    url = f"sqlite:///{tmp_path / 'x.sqlite3'}"
    r = seed_from_live(url, "http://127.0.0.1:9/")
    assert r["seeded"] is False and "not available" in r["reason"]


def test_snapshot_roundtrip(two_archives, tmp_path):
    a, _, a_url, _ = two_archives
    size = write_snapshot(a_url, tmp_path / "snap.sqlite3.gz")
    assert size > 0
    (tmp_path / "snap.sqlite3").write_bytes(gzip.decompress((tmp_path / "snap.sqlite3.gz").read_bytes()))
    assert counts(make_engine(f"sqlite:///{tmp_path / 'snap.sqlite3'}")) == counts(a)


def test_health_check(two_archives, settings, tmp_path):
    a, _, a_url, _ = two_archives
    site = tmp_path / "site"
    export_site(a, replace(settings, database_url=a_url), site, include_archive=False)
    httpd, base = serve(site)
    try:
        assert check_site(base)["ok"]  # live collection off: nothing to complain about
        status = json.loads((site / "data" / "status.json").read_text())
        status["live_enabled"] = True
        status["collector_heartbeat"] = {"cycle_started_at": (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()}
        status["adapters"][0].update(enabled=True, consecutive_failures=20, last_error="http_error: HTTP 403")
        (site / "data" / "status.json").write_text(json.dumps(status))
        result = check_site(base, max_age_minutes=120)
        assert not result["ok"]
        assert any("min ago" in p for p in result["problems"]) and any("20 times" in p for p in result["problems"])
    finally:
        httpd.shutdown()
    assert not check_site("http://127.0.0.1:9/")["ok"]
