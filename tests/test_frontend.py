"""Browser tests for dashboard loading / empty / error states (Chromium via Node Playwright).

Skipped automatically when Node or the `playwright` npm package is unavailable.
"""

import functools
import http.server
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from gso_archive.api.app import create_app
from gso_archive.demo import seed_demo
from gso_archive.export_static import export_site

SCRIPT = Path(__file__).parent / "frontend" / "check_states.cjs"


def _playwright_available() -> bool:
    node = shutil.which("node")
    if not node:
        return False
    return subprocess.run([node, "-e", "require('playwright')"], capture_output=True, cwd=SCRIPT.parent).returncode == 0


pytestmark = pytest.mark.skipif(not _playwright_available(), reason="node + playwright not installed")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def serve_api(settings, engine):
    servers = []

    def start():
        port = _free_port()
        server = uvicorn.Server(uvicorn.Config(create_app(settings, engine), port=port, log_level="warning"))
        threading.Thread(target=server.run, daemon=True).start()
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        servers.append(server)
        return f"http://127.0.0.1:{port}"

    yield start
    for s in servers:
        s.should_exit = True


def run_check(scenario: str, base: str) -> None:
    proc = subprocess.run(["node", str(SCRIPT), scenario, base], capture_output=True, text=True, timeout=180,
                          cwd=SCRIPT.parent)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_empty_states(serve_api):
    run_check("empty", serve_api())


def test_api_error_state(serve_api):
    run_check("api-error", serve_api())


def test_demo_dashboard_renders(serve_api, engine):
    seed_demo(engine, days=35)
    base = serve_api()
    run_check("demo", base)
    run_check("loading", base)
    run_check("interactions", base)
    run_check("refresh", base)


def test_static_site(settings, engine, tmp_path):
    seed_demo(engine, days=10)
    out = tmp_path / "site"
    export_site(engine, settings, out)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        run_check("static", f"http://127.0.0.1:{httpd.server_address[1]}")
    finally:
        httpd.shutdown()
