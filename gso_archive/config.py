"""Runtime configuration, read once from environment variables.

Every tunable (including the collection interval) lives here so it is defined
in exactly one place. See `.env.example` for documentation of each variable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

def _project_root() -> Path:
    """Directory holding web/, data/ and backups/. GSO_HOME wins; otherwise the source
    checkout (when running from it) or the current directory (when pip-installed)."""
    if os.environ.get("GSO_HOME"):
        return Path(os.environ["GSO_HOME"]).resolve()
    source = Path(__file__).resolve().parent.parent
    return source if (source / "web").is_dir() else Path.cwd()


PROJECT_ROOT = _project_root()


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw not in (None, "") else default


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw not in (None, "") else default


def _list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return list(default)
    return [part.strip() for part in raw.split(",") if part.strip()]


# Adapters collected when GSO_ADAPTERS is not set (all verified first-hand on 28 Oct 2026).
DEFAULT_ADAPTERS = [
    "generation_mix",
    "system_demand",
    "tieline_egat",
    "tieline_hvdc",
    "tieline_pltg",
    "power_station",
    "solar_profile",
    "solar_forecast",
    "genmix_live",
    "other_re",  # after genmix_live: it is dated by the home page reading of the same run
    "availability",
    "solar_farms",
]


@dataclass(frozen=True)
class Settings:
    database_url: str
    raw_store_dir: Path
    raw_retention: str  # "all" | "changed" | "none"

    gso_base_url: str
    # Live access to the GSO website is opt-in. See docs/SOURCE_INVESTIGATION.md
    # (terms of use) before enabling.
    gso_live_enabled: bool
    adapters: list[str]
    user_agent: str

    collect_interval_seconds: int
    request_delay_seconds: float
    request_timeout_seconds: float
    max_retries: int
    revision_recheck_minutes: int
    auto_backfill_days: int
    auto_backfill_per_cycle: int

    # GET each GSO page before asking it for data, like a browser. Off: the data addresses answer without it,
    # and skipping it saves GSO ~350 KB per run.
    warm_up: bool = False
    # "github" (Actions + Pages) or "worker" (always-on `schedule`): shown on the site's Auto labels
    collection_mode: str = "worker"
    api_cors_origins: list[str] = field(default_factory=list)
    admin_token: str = ""
    web_dir: Path = PROJECT_ROOT / "web"


def load_settings() -> Settings:
    default_db = f"sqlite:///{(PROJECT_ROOT / 'data' / 'archive.sqlite3').as_posix()}"
    return Settings(
        database_url=os.environ.get("DATABASE_URL") or default_db,
        raw_store_dir=Path(os.environ.get("RAW_STORE_DIR") or PROJECT_ROOT / "data" / "raw"),
        raw_retention=os.environ.get("RAW_RETENTION", "changed").lower(),
        gso_base_url=os.environ.get("GSO_BASE_URL", "https://www.gso.org.my").rstrip("/"),
        gso_live_enabled=_bool("GSO_LIVE_ENABLED", False),
        adapters=_list("GSO_ADAPTERS", DEFAULT_ADAPTERS),
        user_agent=os.environ.get(
            "GSO_USER_AGENT",
            "gso-data-archive/2.0 (+https://github.com/Darren38/gso-data-archive)",
        ),
        collect_interval_seconds=_int("COLLECT_INTERVAL_SECONDS", 120),
        request_delay_seconds=_float("GSO_REQUEST_DELAY_SECONDS", 2.0),
        request_timeout_seconds=_float("GSO_REQUEST_TIMEOUT_SECONDS", 30.0),
        max_retries=_int("GSO_MAX_RETRIES", 3),
        revision_recheck_minutes=_int("GSO_REVISION_RECHECK_MINUTES", 60),
        auto_backfill_days=_int("GSO_AUTO_BACKFILL_DAYS", 7),
        auto_backfill_per_cycle=_int("GSO_AUTO_BACKFILL_PER_CYCLE", 2),
        collection_mode=os.environ.get("GSO_COLLECTION_MODE", "worker"),
        warm_up=_bool("GSO_WARM_UP", False),
        api_cors_origins=_list("API_CORS_ORIGINS", []),
        admin_token=os.environ.get("ADMIN_TOKEN", ""),
    )
