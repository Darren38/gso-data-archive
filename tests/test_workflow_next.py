"""The `next` job of archive.yml keeps collection going: each run must start the next one, and a run GitHub never starts
must be replaced. Its shell script is run against a stand-in `gh` in every situation seen so far (CLAUDE.md lesson 61):
on 20 Nov 2026 an older run still finishing its backup was taken for the next collection and collection stopped for
an hour. Skipped when bash or jq is missing."""

import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent

FAKE_GH = textwrap.dedent('''\
    #!/usr/bin/env python3
    import json, os, subprocess, sys
    T = os.environ["T"]; f = f"{T}/runs.json"; runs = json.load(open(f)); scen = os.environ["SCEN"]; a = sys.argv[1:]
    log = open(f"{T}/log", "a")
    if a[:2] == ["workflow", "run"]:
        nid = max(r["id"] for r in runs) + 1
        stuck = scen == "stuck" or (scen == "stuck_once" and not any(r["id"] > 100 for r in runs))
        runs.append({"id": nid, "status": "queued" if stuck else "in_progress", "conclusion": None})
        log.write(f"start {nid} {'stuck' if stuck else 'ok'}\\n")
    elif a[:2] == ["run", "cancel"]:
        for r in runs:
            if r["id"] == int(a[2]):
                r["status"], r["conclusion"] = "completed", "cancelled"
        log.write(f"cancel {a[2]}\\n")
    elif a[0] == "api":
        jq = a[a.index("--jq") + 1]
        print(subprocess.run(["jq", "-r", jq], input=json.dumps({"workflow_runs": runs}), capture_output=True, text=True).stdout.strip())
    json.dump(runs, open(f, "w"))
''')

CASES = {
    # situation: (runs GitHub lists when this run (id 100) finishes, how new runs behave, expected gh calls)
    "healthy": ([{"id": 100, "status": "in_progress"}], "ok", ["start 101 ok"]),
    "older run still finishing (20 Nov)": ([{"id": 100, "status": "in_progress"}, {"id": 98, "status": "in_progress"}], "ok", ["start 101 ok"]),
    "old stuck run ignored (16 Nov)": ([{"id": 100, "status": "in_progress"}, {"id": 99, "status": "queued"}], "ok", ["start 101 ok"]),
    "newer run already running": ([{"id": 100, "status": "in_progress"}, {"id": 101, "status": "in_progress"}], "ok", []),
    "newer run waiting its turn": ([{"id": 100, "status": "in_progress"}, {"id": 101, "status": "pending"}], "ok", []),
    "new run stuck once": ([{"id": 100, "status": "in_progress"}], "stuck_once", ["start 101 stuck", "cancel 101", "start 102 ok"]),
    "new runs always stuck": ([{"id": 100, "status": "in_progress"}], "stuck",
                              ["start 101 stuck", "cancel 101", "start 102 stuck", "cancel 102", "start 103 stuck"]),
}


@pytest.mark.skipif(not (shutil.which("bash") and shutil.which("jq")), reason="bash and jq needed")
@pytest.mark.parametrize("name", CASES)
def test_next_job_keeps_collection_going(name, tmp_path):
    runs, scen, expected = CASES[name]
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "archive.yml").read_text())
    script = wf["jobs"]["next"]["steps"][0]["run"].replace("${{ github.run_id }}", "100")
    script = script.replace("sleep 60", "sleep 0").replace("sleep 30", "sleep 0").replace('sleep "$wait"', "sleep 0")
    (tmp_path / "step.sh").write_text(script)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text(FAKE_GH)
    (bin_dir / "gh").chmod(0o755)
    (tmp_path / "runs.json").write_text(json.dumps([{**r, "conclusion": None} for r in runs]))
    (tmp_path / "log").write_text("")
    env = {**os.environ, "T": str(tmp_path), "SCEN": scen, "GITHUB_REPOSITORY": "x/y", "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    r = subprocess.run(["bash", "-e", str(tmp_path / "step.sh")], env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "log").read_text().split("\n")[:-1] == expected, (tmp_path / "log").read_text()
