"""Print what `gso-archive probe` found, readably, into the GitHub Actions log.

    python scripts/probe_summary.py probe.json probe-out
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

INTERESTING = re.compile(r"aspx/\w+|PageMethods|\$\.ajax|fetch\(|url\s*:|contentType|JSON\.stringify|Fromdate|Todate|"
                         r"Highcharts|Chart\(|amCharts|series\s*:|categories|<select|<input[^>]+date|disclaimer|terms", re.I)


def main(report_path: str, out_dir: str) -> None:
    text = Path(report_path).read_text(encoding="utf-8", errors="replace")
    start = text.find("{")
    report = json.loads(text[start:]) if start >= 0 else {}
    print("=" * 100)
    print("PAGES")
    for page, info in report.get("pages", {}).items():
        print(f"\n## {page}: " + (info.get("error") or f"HTTP {info.get('status')} {info.get('bytes')} bytes"))
        for key in ("page_methods", "pagemethods_js", "ajax_urls", "fetch_urls", "json_bodies", "chart_libs",
                    "system_data_links", "script_src", "form_inputs"):
            if info.get(key):
                print(f"   {key}: {info[key][:40]}")
    print("\n" + "=" * 100)
    print("DATA ADDRESSES TRIED")
    for name, m in report.get("methods", {}).items():
        print(f"\n## {name}: status={m.get('status')} records={m.get('records')} error={m.get('error') or m.get('decode_error')}")
        if m.get("fields"):
            print(f"   fields: {m['fields']}")
        for row in (m.get("sample") or [])[:3]:
            print(f"   sample: {json.dumps(row)[:400]}")
    saved = Path(report.get("saved_to") or out_dir)
    folders = [saved] if saved.is_dir() and list(saved.glob("*.html")) else sorted(Path(out_dir).glob("*"))
    for folder in folders[-1:]:
        print("\n" + "=" * 100)
        print(f"SCRIPT LINES THAT LOAD DATA ({folder})")
        for html in sorted(folder.glob("*.html")):
            lines = html.read_text(encoding="utf-8", errors="replace").splitlines()
            hits = [i for i, line in enumerate(lines) if INTERESTING.search(line)]
            print(f"\n## {html.name}: {len(hits)} matching lines")
            for i in hits[:60]:
                print(f"   {i + 1:5d}: {lines[i].strip()[:300]}")
        for raw in sorted(folder.glob("*__*.json")):
            print(f"\n## raw answer {raw.name}: {raw.read_text(encoding='utf-8', errors='replace')[:1500]}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
