"""The numbers the pages work out in the browser (web/js/analysis.js), checked with Node on readings whose answers
are known. Skipped when Node is not installed."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "frontend" / "check_analysis.mjs"


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_browser_calculations():
    r = subprocess.run([shutil.which("node"), str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr or r.stdout
