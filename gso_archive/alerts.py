"""Which problems email the owner (owner, 20 Nov 2026: "only send meaningful and important updates").

GitHub emails the owner when a run fails, and only the hourly check is allowed to fail a run. It fails only for a
problem that is new, or that has lasted another whole day since it was last emailed; a problem that is still there an
hour later is listed on the check's page but sends nothing. A problem that goes away is forgotten, so if it comes
back it emails again. The list of emailed problems is kept between checks in the Actions cache (`health-state-`).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

REMIND_AFTER = timedelta(hours=24)


def problem_id(text: str) -> str:
    """The same problem with different figures ("failed 13 times", "failed 14 times") has one id."""
    return re.sub(r"\d[\d,.:]*", "#", text)[:200]


def load(path: Path | None) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path and path.exists() else {}
    except (OSError, ValueError):
        return {}  # damaged or old state: start again (it only decides whether to email)


def decide(problems: list[str], state: dict, now: datetime) -> tuple[list[str], list[str], dict]:
    """(problems to email now, problems already emailed, new state)."""
    emailed = {k: v for k, v in (state.get("emailed") or {}).items() if isinstance(v, str)}
    send, quiet, keep = [], [], {}
    for p in problems:
        pid = problem_id(p)
        when = emailed.get(pid)
        try:
            due = when is None or now - datetime.fromisoformat(when) >= REMIND_AFTER
        except ValueError:
            due = True
        (send if due else quiet).append(p)
        keep[pid] = now.isoformat() if due else when
    return send, quiet, {**state, "emailed": keep, "checked_at": now.isoformat()}


def save(path: Path | None, state: dict) -> None:
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=1), encoding="utf-8")
