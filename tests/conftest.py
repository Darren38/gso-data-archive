import json
import os
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from gso_archive.config import load_settings
from gso_archive.db import make_engine
from gso_archive.http import GsoClient
from gso_archive.migrations import migrate

FIXTURES = Path(__file__).parent / "fixtures"
TEST_BASE = "http://gso.test"


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


@pytest.fixture
def settings(tmp_path):
    base = load_settings()
    return replace(
        base,
        database_url=os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test.sqlite3'}",
        raw_store_dir=tmp_path / "raw",
        raw_retention="changed",
        gso_base_url=TEST_BASE,
        gso_live_enabled=False,
        adapters=["generation_mix", "system_demand"],
        request_delay_seconds=0.0,
        max_retries=2,
        auto_backfill_days=4,
        auto_backfill_per_cycle=2,
        web_dir=Path(__file__).resolve().parent.parent / "web",
    )


@pytest.fixture
def engine(settings):
    eng = make_engine(settings.database_url)
    if eng.dialect.name == "postgresql":  # isolate each test on a shared PG database
        from gso_archive import db

        db.metadata.drop_all(eng)
    migrate(eng)
    yield eng
    eng.dispose()


class FakeGso:
    """httpx MockTransport standing in for the GSO site. Routes: (page, method) → response list."""

    def __init__(self):
        self.routes: dict[str, list] = {}
        self.calls: list[httpx.Request] = []

    def add(self, path: str, *responses):
        self.routes.setdefault(path, []).extend(responses)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        path = request.url.path.lstrip("/")
        if request.method == "GET":
            return httpx.Response(200, text="<html>page</html>")
        queue = self.routes.get(path)
        if not queue:
            return httpx.Response(404, text="not found")
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        if isinstance(item, int):
            return httpx.Response(item, text="error")
        if isinstance(item, str):
            item = fixture_bytes(item)
        return httpx.Response(200, content=item, headers={"content-type": "application/json; charset=utf-8"})

    def posts(self, path_fragment: str = "") -> list[httpx.Request]:
        return [c for c in self.calls if c.method == "POST" and path_fragment in c.url.path]

    def bodies(self, path_fragment: str = "") -> list[dict]:
        return [json.loads(c.content) for c in self.posts(path_fragment)]


@pytest.fixture
def fake():
    return FakeGso()


@pytest.fixture
def client(settings, fake):
    c = GsoClient(settings, transport=httpx.MockTransport(fake.handler))
    yield c
    c.close()
