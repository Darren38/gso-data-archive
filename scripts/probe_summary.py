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
    print("\n" + "=" * 100)
    print("PAGE SCRIPTS AND THEIR DATA CALLS")
    for url, info in report.get("scripts", {}).items():
        print(f"\n## {url}: {info.get('error') or str(info.get('bytes')) + ' bytes'}")
        for call in info.get("calls", []):
            print(f"\n   line {call['line']}: {call['url']}")
            for ln in call["context"]:
                print(f"      | {ln}")
    print("\n" + "=" * 100)
    print("RAW STARTS OF SCRIPT-CALL ANSWERS")
    for name, m in report.get("methods", {}).items():
        if m.get("raw_start"):
            print(f"\n## {name}: {m['raw_start'][:1200]}")
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
        # The page code around data GSO sends without names (headline figures, cross-border forecasts), so their
        # meaning comes from GSO's own code rather than a guess.
        unnamed = re.compile(r"GetFeatureSectionData|function checkLoading|HighEnergyRecData\.mw|RenewalData\.mw|BESSData\.mw|"
                             r"COWData\.mw|id=\"(currentgriddemand|currentsystemdemand|highestdemandrecorded|target\d)\"|"
                             r"ForecastChart|yAxes|<h\d|<title|GetSolarMap|HistoricalData|endDateStr\s*=")
        for html in sorted(folder.glob("*.html")):
            lines = html.read_text(encoding="utf-8", errors="replace").splitlines()
            hits = [i for i, line in enumerate(lines) if unnamed.search(line)]
            if hits:
                print(f"\n## code around unlabelled data in {html.name}: {len(hits)} places")
            shown = -1
            for i in hits[:30]:
                if i <= shown:
                    continue
                print(f"\n   --- line {i + 1}")
                for j in range(max(0, i - 12), min(len(lines), i + 90)):
                    print(f"   {j + 1:5d}: {lines[j].rstrip()[:300]}")
                shown = i + 90
        # How GSO's own scripts read and label the data (series names, splitting of "$"-joined answers, units).
        keys = re.compile(r"split\(|name\s*:|\.d\b|series|title|text\s*:|forecast|actual|lss|dn\b|rooftop|transmission|"
                          r"distribution|grid|capacity|irradiance|function\s+\w+|\[\d\]|MW|MWp|%", re.I)
        for js in sorted(folder.glob("script_*.js")):
            lines = js.read_text(encoding="utf-8", errors="replace").splitlines()
            hits = [i for i, line in enumerate(lines) if keys.search(line) and len(line.strip()) > 2]
            print(f"\n## how {js.name} reads the data: {len(hits)} lines")
            for i in hits[:700]:
                print(f"   {i + 1:5d}: {lines[i].strip()[:220]}")
        # GSO's chart colours: the chartColors table and every series' name/colour pair.
        for js in sorted(folder.glob("script_*.js")):
            lines = js.read_text(encoding="utf-8", errors="replace").splitlines()
            hits = [i for i, line in enumerate(lines) if re.search(r"chartColors|gso\w*\s*:|color\s*:|#[0-9a-fA-F]{6}|rgba?\(", line)]
            print(f"\n## colours in {js.name}: {len(hits)} lines")
            for i in hits[:400]:
                name = next((lines[j].strip()[:60] for j in range(i, max(-1, i - 4), -1) if "name:" in lines[j]), "")
                print(f"   {i + 1:5d}: {lines[i].strip()[:160]}   {('<- ' + name) if name else ''}")
        # Whole bodies of the functions that turn GSO's answers into charts.
        wanted = {"DrawGenMixChart": 50, "DrawSolarMap": 45, "getData": 60, "DrawSolarChart": 40, "DrawSysAvPieChart": 25,
                  "DrawGenMixPieChart": 40}
        for js in sorted(folder.glob("script_*.js")):
            lines = js.read_text(encoding="utf-8", errors="replace").splitlines()
            for name, count in wanted.items():
                for i, line in enumerate(lines):
                    if re.search(rf"function\s+{name}\s*\(", line):
                        print(f"\n## {js.name}: function {name} (line {i + 1})")
                        for j in range(i, min(len(lines), i + count)):
                            print(f"   {j + 1:5d}| {lines[j].rstrip()[:240]}")
            for i, line in enumerate(lines):  # the chart series list for the generation-mix chart
                if re.search(r"name:\s*'(Grid Demand|System Demand|BESS|Tie-Line)'", line):
                    print(f"\n## {js.name}: series near line {i + 1}")
                    for j in range(max(0, i - 2), min(len(lines), i + 5)):
                        print(f"   {j + 1:5d}| {lines[j].rstrip()[:240]}")
        for raw in sorted(folder.glob("*__*.json")):
            print(f"\n## raw answer {raw.name}: {raw.read_text(encoding='utf-8', errors='replace')[:1500]}")

    # The home page's headline boxes, whole: each figure's label and unit (e.g. "Highest Energy Recorded").
    for folder in folders[-1:]:
        for html in sorted(folder.glob("*.html")):
            lines = html.read_text(encoding="utf-8", errors="replace").splitlines()
            boxes = [i for i, line in enumerate(lines) if re.search(r'id="target\d"', line)]
            if boxes:
                print(f"\n## headline boxes in {html.name}")
            for i in boxes:
                print("   ---")
                for j in range(i, min(len(lines), i + 16)):
                    print(f"   {j + 1:5d}: {lines[j].rstrip()[:200]}")

    # Last, because GitHub's log download returns only the final 5,000 lines: GSO's complete answers.
    print("\n" + "=" * 100)
    print("FULL ANSWERS (for test fixtures)")
    for name, m in report.get("methods", {}).items():
        if m.get("raw_full") and re.search(r"Solar|GenMix|SysAV|OtherRE|LastAvailable|PowerStation|FeatureSection|"
                                           r"ForecastChart", name):
            print(f"\n## FULL {name}\n{m['raw_full']}\n## END")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
