"""Local stand-in for the GSO site, serving the SYNTHETIC test fixtures over HTTP.

Used to validate the full pipeline end to end (CLI → HTTP → parser → DB → API)
without contacting gso.org.my:

    python scripts/fixture_server.py 8901 &
    GSO_BASE_URL=http://127.0.0.1:8901 python -m gso_archive collect

Responds to the documented PageMethod paths. The DT/Tarikhmasa timestamps are
rewritten to the requested Fromdate so backfills over several days produce
distinct readings.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FIX = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
ROUTES = {
    "/SystemData/CurrentGen.aspx/GetChartDataSource": "currentgen_2026-10-27.json",
    "/SystemData/SystemDemand.aspx/GetChartDataSource": "demand_2026-10-27.json",
    "/SystemData/TieLine.aspx/GetChartDataSource": "tieline_pltg_2026-10-27.json",
    "/SystemData/PowerStation.aspx/GetDataSource": "powerstation.json",
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><body>fixture server</body></html>")

    def do_POST(self):
        name = ROUTES.get(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if not name:
            self.send_response(404)
            self.end_headers()
            return
        outer = json.loads((FIX / name).read_text())
        rows = json.loads(outer["d"])
        if "Fromdate" in body:
            day = datetime.strptime(body["Fromdate"], "%d/%m/%Y").date().isoformat()
            for row in rows:
                for key in ("DT", "Tarikhmasa"):
                    if key in row:
                        row[key] = day + row[key][10:]
        payload = json.dumps({"d": json.dumps(rows)}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8901
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
