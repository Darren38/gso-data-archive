"""Source investigation helper: `gso-archive probe`.

Run this from a network that can reach www.gso.org.my (and only after reviewing
GSO's terms of use). It fetches each SystemData page *once*, extracts the
PageMethod names / AJAX URLs / form fields referenced by the page's HTML and
scripts, optionally tries the discovered methods for today's date, and saves
everything under PROBE_DIR so the findings can be reviewed and committed as
test fixtures. It never submits credentials, solves CAPTCHAs, or loops.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from .adapters import ADAPTERS
from .adapters.base import decode_pagemethod, schema_signature
from .config import Settings
from .http import FetchError, GsoClient
from .timeutil import gso_date_param, myt_today, utcnow

PAGES = [
    "",
    "LandingPage.aspx",
    "SystemData/Solar.aspx",
    "SystemData/CurrentGen.aspx",
    "SystemData/SystemDemand.aspx",
    "SystemData/TieLine.aspx",
    "SystemData/PowerStation.aspx",
    "SystemData/CBPE.aspx",
]

PATTERNS = {
    "page_methods": re.compile(r"[\w/]+\.aspx/(\w+)"),
    "pagemethods_js": re.compile(r"PageMethods\.(\w+)\s*\("),
    "ajax_urls": re.compile(r"""url\s*:\s*['"]([^'"]+)['"]"""),
    "fetch_urls": re.compile(r"""fetch\(\s*['"]([^'"]+)['"]"""),
    "json_bodies": re.compile(r"""data\s*:\s*(['"]?\{[^}]{0,300}\}['"]?)"""),
    "system_data_links": re.compile(r"""href=['"]([^'"]*SystemData/[^'"]+)['"]""", re.I),
    "script_src": re.compile(r"""<script[^>]+src=['"]([^'"]+)['"]""", re.I),
    "form_inputs": re.compile(r"""<(?:input|select)[^>]+(?:name|id)=['"]([^'"]+)['"]""", re.I),
    "chart_libs": re.compile(r"(highcharts|chart\.js|amcharts|echarts|plotly|google\.visualization|canvasjs)", re.I),
    "terms_mentions": re.compile(r"([^<>]{0,200}(?:terms|disclaimer|copyright|consent|hak cipta)[^<>]{0,200})", re.I),
}


def _extract(html: str) -> dict:
    out = {}
    for name, pattern in PATTERNS.items():
        found = sorted({m.strip() for m in pattern.findall(html)})
        out[name] = found[:100]
    return out


# Page-specific scripts that load data (the Solar page and the home page keep their data calls in separate files).
SCRIPT_HINT = re.compile(r"solar|landing", re.I)
SKIP_METHODS = re.compile(r"download|admin|access|quicklink|news", re.I)
AJAX_URL = re.compile(r"""url\s*:\s*["']([^"']*?\.aspx/\w+)["']""", re.I)
TIELINES = ["HVDC", "PLTG", "EGAT"]


def _probe_scripts(client: GsoClient, settings: Settings, report: dict, out_dir: Path, day: date) -> None:
    """Read the page-specific scripts, note every data call with the code around it, and try each call once."""
    from urllib.parse import urljoin

    report["scripts"] = {}
    seen: set[str] = set()
    for page, info in list(report["pages"].items()):
        page_url = f"{settings.gso_base_url}/{'' if page == '/' else page}"
        for src in info.get("script_src", []):
            if not SCRIPT_HINT.search(src) or src.startswith("http") and settings.gso_base_url not in src:
                continue
            url = urljoin(page_url, src)
            if url in seen:
                continue
            seen.add(url)
            try:
                res = client.get(url, accept="*/*")  # GSO answers 406 to a JSON/HTML-only Accept for .js files
            except FetchError as exc:
                report["scripts"][url] = {"error": str(exc)}
                continue
            js = res.content.decode("utf-8", errors="replace")
            (out_dir / ("script_" + Path(src).name)).write_text(js, encoding="utf-8")
            lines = js.splitlines()
            calls = []
            for i, line in enumerate(lines):
                m = AJAX_URL.search(line)
                if m:
                    calls.append({"line": i + 1, "url": m.group(1),
                                  "context": [ln.strip()[:200] for ln in lines[max(0, i - 6): i + 10]]})
            report["scripts"][url] = {"bytes": len(js), "calls": calls}
            for call in calls:
                method_url = urljoin(page_url, call["url"])  # AJAX addresses resolve against the page, not the script
                if SKIP_METHODS.search(call["url"]) or method_url in report["methods"]:
                    continue
                bodies = [{}]
                ctx = " ".join(call["context"])
                if re.search(r"fromdate|todate", ctx, re.I):
                    bodies.append({"Fromdate": gso_date_param(day), "Todate": gso_date_param(day)})
                for body in bodies:
                    key = f"{method_url} {json.dumps(body)}"
                    entry: dict = {"url": method_url, "request": body}
                    try:
                        mres = client.post_pagemethod(method_url, body, referer=page_url)
                        entry["status"] = mres.status
                        entry["raw_start"] = mres.content[:1500].decode("utf-8", errors="replace")
                        entry["raw_full"] = mres.content[:30000].decode("utf-8", errors="replace")
                        try:
                            records = decode_pagemethod(mres.content)
                            entry.update(records=len(records), fields=schema_signature(records), sample=records[:3])
                        except Exception as exc:  # noqa: BLE001
                            entry["decode_error"] = str(exc)
                    except FetchError as exc:
                        entry["error"] = f"{exc.error_type}: {exc}"
                    report["methods"][key] = entry
    # The home page's own (inline) data calls, e.g. GetSolarActualData / GetSolarForecastData.
    landing = report["pages"].get("LandingPage.aspx", {})
    for method in landing.get("page_methods", []):
        if SKIP_METHODS.search(method) or not re.search(r"solar|genmix|otherre|feature|current|sys", method, re.I):
            continue
        method_url = f"{settings.gso_base_url}/LandingPage.aspx/{method}"
        entry = {"url": method_url, "request": {}}
        try:
            mres = client.post_pagemethod(method_url, {}, referer=f"{settings.gso_base_url}/LandingPage.aspx")
            entry["status"] = mres.status
            entry["raw_start"] = mres.content[:1500].decode("utf-8", errors="replace")
            entry["raw_full"] = mres.content[:30000].decode("utf-8", errors="replace")
            try:
                records = decode_pagemethod(mres.content)
                entry.update(records=len(records), fields=schema_signature(records), sample=records[:3])
            except Exception as exc:  # noqa: BLE001
                entry["decode_error"] = str(exc)
        except FetchError as exc:
            entry["error"] = f"{exc.error_type}: {exc}"
        report["methods"][f"LandingPage.aspx/{method}"] = entry
    # Tie-lines need a Line parameter.
    base = f"{settings.gso_base_url}/SystemData/TieLine.aspx"
    for line in TIELINES:
        body = {"Fromdate": gso_date_param(day), "Todate": gso_date_param(day), "Line": line}
        entry = {"url": f"{base}/GetChartDataSource", "request": body}
        try:
            mres = client.post_pagemethod(f"{base}/GetChartDataSource", body, referer=base)
            entry["status"] = mres.status
            records = decode_pagemethod(mres.content)
            entry.update(records=len(records), fields=schema_signature(records), sample=records[:3])
        except Exception as exc:  # noqa: BLE001
            entry["error"] = str(exc)[:300]
        report["methods"][f"TieLine {line}"] = entry


def run_probe(settings: Settings, out_dir: Path, try_methods: bool = True, day: date | None = None) -> dict:
    day = day or myt_today()
    out_dir = Path(out_dir) / utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict = {"base_url": settings.gso_base_url, "probed_at": utcnow().isoformat(), "pages": {}, "methods": {}}
    with GsoClient(settings) as client:
        for page in PAGES:
            url = f"{settings.gso_base_url}/{page}"
            try:
                res = client.get(url)
            except FetchError as exc:
                report["pages"][page or "/"] = {"error": f"{exc.error_type}: {exc}"}
                if exc.error_type == "live_disabled":
                    break
                continue
            html = res.content.decode("utf-8", errors="replace")
            name = (page or "index").replace("/", "_")
            (out_dir / f"{name}.html").write_text(html, encoding="utf-8")
            report["pages"][page or "/"] = {"status": res.status, "bytes": len(res.content), **_extract(html)}
            if not try_methods or not page.startswith("SystemData/"):
                continue
            methods = set(report["pages"][page]["page_methods"]) | set(report["pages"][page]["pagemethods_js"])
            known = [s.method for s in ADAPTERS.values() if s.page == page]
            for method in sorted(methods | set(known)):
                murl = f"{url}/{method}"
                body = {"Fromdate": gso_date_param(day), "Todate": gso_date_param(day)}
                entry: dict = {"url": murl, "request": body}
                try:
                    mres = client.post_pagemethod(murl, body, referer=url)
                    entry["status"] = mres.status
                    (out_dir / f"{name}__{method}.json").write_bytes(mres.content)
                    try:
                        records = decode_pagemethod(mres.content)
                        entry["records"] = len(records)
                        entry["fields"] = schema_signature(records)
                        entry["sample"] = records[:3]
                    except Exception as exc:  # report, don't crash the probe
                        entry["decode_error"] = str(exc)
                except FetchError as exc:
                    entry["error"] = f"{exc.error_type}: {exc}"
                report["methods"][f"{page}/{method}"] = entry
        _probe_scripts(client, settings, report, out_dir, day)
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    report["saved_to"] = str(out_dir)
    return report
