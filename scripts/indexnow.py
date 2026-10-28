"""Tell search engines the site has changed, through IndexNow.

    python scripts/indexnow.py submit   after a push to main has been published (the "indexnow" job in archive.yml)

IndexNow (https://www.indexnow.org) is a free, open protocol used by Bing, Yandex, Seznam, Naver and others: a site
lists the addresses that changed and the search engines fetch those pages soon after. Google does not take part; it
finds the site through sitemap.xml.

The site is rebuilt every few minutes with new readings, but the page itself only changes when the code does, so this
runs only after a push. It waits until the live page is the one just pushed (GitHub Pages can keep the old copy for a
few minutes), then sends the address once. The same way as Tech Comparison Hub's tools/indexnow.py.

The key (web/indexnow.txt) is public by design: it is served at <site>/indexnow.txt so the search engines can check
that a submission for this site comes from its owner. It grants no access to anything.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://darren38.github.io/gso-data-archive/"
KEY_FILE = "indexnow.txt"
ENDPOINT = "https://api.indexnow.org/indexnow"
UA = "gso-data-archive (IndexNow)"  # names the project, never the owner
URLS = [BASE]


def get(url: str, timeout: int = 30) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def wait_until_live(key: str, minutes: int = 15) -> bool:
    """True once the live page and key file match what was pushed. Pages can take a few minutes, and its cache
    keeps the old copy for up to ten more."""
    want = hashlib.sha256((ROOT / "web" / "index.html").read_bytes()).hexdigest()
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        page = get(f"{BASE}?v={int(time.time())}")  # a fresh address, so no cached copy answers
        served = (get(f"{BASE}{KEY_FILE}?v={int(time.time())}") or b"").decode("utf-8", "replace").strip()
        if page and hashlib.sha256(page).hexdigest() == want and served == key:
            return True
        time.sleep(30)
    return False


def submit() -> int:
    key = (ROOT / "web" / KEY_FILE).read_text(encoding="utf-8").strip()
    if not wait_until_live(key):
        print("::warning::IndexNow: the new version did not appear on the live site in time; nothing sent.")
        return 0
    body = json.dumps({"host": "darren38.github.io", "key": key, "keyLocation": BASE + KEY_FILE, "urlList": URLS}).encode("utf-8")
    meaning = {400: "bad request", 403: "key not accepted", 422: "addresses do not belong to the key's location",
               429: "too many requests"}
    # IndexNow can answer 403 while it is still checking a key it has not seen before, and 429 or a server error
    # clears by itself; 400 and 422 would not change, so they are not repeated.
    waits = [120, 300]
    for attempt in range(len(waits) + 1):
        req = urllib.request.Request(ENDPOINT, data=body, method="POST",
                                     headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                print(f"[indexnow] sent {len(URLS)} address(es): HTTP {r.status}" + (f" (attempt {attempt + 1})" if attempt else ""))
            return 0
        except urllib.error.HTTPError as e:
            problem, again = f"HTTP {e.code} {meaning.get(e.code, '')}".strip(), e.code in (403, 429) or e.code >= 500
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            problem, again = f"could not be reached ({type(e).__name__})", True
        if not again or attempt == len(waits):
            break
        print(f"[indexnow] {problem}; trying again in {waits[attempt] // 60} minutes")
        time.sleep(waits[attempt])
    print(f"::warning::IndexNow: {problem} after {attempt + 1} attempt(s); the search engines still find the site "
          "through sitemap.xml.")
    return 0  # telling search engines is a courtesy: it never fails the run


if __name__ == "__main__":
    if sys.argv[1:] != ["submit"]:
        print(__doc__)
        sys.exit(2)
    sys.exit(submit())
