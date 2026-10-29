"""Publish the site built by this run to GitHub Pages, and wait until that copy is live.

    python scripts/deploy_pages.py      in the "deploy" job of archive.yml (needs pages: write and id-token: write)

Does what actions/deploy-pages does, with one difference that matters here. GitHub identifies a Pages deployment by
its "pages_build_version", which GitHub's API describes as "a unique string". deploy-pages always sends the commit, but
this site is republished every few minutes from the same commit, so hundreds of deployments shared one identity:
GitHub kept serving one older copy, and deploy-pages, which checks the deployment with that same identity, reported
"success" within seconds every time. Found on 29 October 2026, when the live site stayed hours behind the archive.

Here every run gets its own version (commit, run number and attempt), and the script waits for that deployment.

Environment: GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_SHA, GITHUB_RUN_ID, GITHUB_RUN_ATTEMPT, GITHUB_API_URL,
ACTIONS_ID_TOKEN_REQUEST_URL and ACTIONS_ID_TOKEN_REQUEST_TOKEN (set by GitHub), ARTIFACT_ID (from
actions/upload-pages-artifact), and GITHUB_OUTPUT to pass page_url on.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

SUCCEEDED = "succeed"
FAILED = {  # final; the same list as deploy-pages
    "deployment_failed": "Deployment failed, try again later.",
    "deployment_content_failed": "Artifact could not be deployed. Check its contents (one tar file, no symlinks).",
    "deployment_cancelled": "Deployment cancelled.",
    "deployment_lost": "Deployment failed to report final status.",
}
UA = "gso-data-archive (deploy)"


def build_version(env: dict) -> str:
    """Unique per run and attempt, and still shows which commit it was built from."""
    return f"{env['GITHUB_SHA']}-run{env['GITHUB_RUN_ID']}-{env.get('GITHUB_RUN_ATTEMPT', '1')}"


def request(method: str, url: str, token: str | None = None, body: dict | None = None, timeout: float = 30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": UA,
        **({"Authorization": f"Bearer {token}"} if token else {}),
        **({"Content-Type": "application/json"} if data else {}),
    })
    with urllib.request.urlopen(req, timeout=timeout) as res:
        raw = res.read()
        return json.loads(raw) if raw else {}


def _body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", "replace")[:500]
    except Exception:  # noqa: BLE001
        return ""


def oidc_token(env: dict, req=request) -> str:
    # What @actions/core getIDToken() does without an audience.
    return req("GET", env["ACTIONS_ID_TOKEN_REQUEST_URL"], env["ACTIONS_ID_TOKEN_REQUEST_TOKEN"])["value"]


def deploy(env: dict, req=request, sleep=time.sleep, timeout_s: float = 600, every_s: float = 5) -> dict:
    """Create the deployment and wait for it. Returns the final status; raises SystemExit on failure."""
    api = env.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    base = f"{api}/repos/{env['GITHUB_REPOSITORY']}/pages/deployments"
    token, version = env["GITHUB_TOKEN"], build_version(env)
    try:
        created = req("POST", base, token, {"artifact_id": int(env["ARTIFACT_ID"]), "pages_build_version": version,
                                            "oidc_token": oidc_token(env, req)})
    except urllib.error.HTTPError as exc:
        # Seen on 29 Oct 2026: a build version that isn't a commit was refused with 404. Show GitHub's reason and
        # publish under the commit (what deploy-pages does) so the site is never left unpublished.
        print(f"Build version {version} refused: HTTP {exc.code} {_body(exc)}")
        version = env["GITHUB_SHA"]
        created = req("POST", base, token, {"artifact_id": int(env["ARTIFACT_ID"]), "pages_build_version": version,
                                            "oidc_token": oidc_token(env, req)})
    dep_id = created.get("id") or (created.get("status_url") or "").rstrip("/").split("/")[-1] or version
    print(f"Created deployment {dep_id} for build version {version}")
    status_url = created.get("status_url") or f"{base}/{dep_id}"
    waited = 0.0
    while True:
        try:
            state = req("GET", status_url, token)
        except urllib.error.HTTPError as exc:
            print(f"Status check: HTTP {exc.code} {_body(exc)}")
            state = {"status": f"http_{exc.code}"}
        status = state.get("status")
        if status == SUCCEEDED:
            print(f"Live: {created.get('page_url') or ''} (build version {version})")
            return {**state, "page_url": created.get("page_url", "")}
        if status in FAILED:
            raise SystemExit(f"{FAILED[status]} (deployment {dep_id})")
        if waited >= timeout_s:
            try:
                req("POST", f"{base}/{dep_id}/cancel", token)
            except Exception:  # noqa: BLE001 - best effort
                pass
            raise SystemExit(f"Deployment {dep_id} did not finish within {timeout_s:.0f} s (last status: {status})")
        print(f"Status: {status}")
        sleep(every_s)
        waited += every_s


def main() -> int:
    env = dict(os.environ)
    result = deploy(env)
    out = env.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"page_url={result.get('page_url', '')}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
