"""scripts/deploy_pages.py: every run publishes under its own build version and waits for that deployment."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("deploy_pages", Path(__file__).parent.parent / "scripts" / "deploy_pages.py")
dp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dp)

ENV = {"GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": "Darren38/gso-data-archive", "GITHUB_SHA": "e32f370c", "GITHUB_RUN_ID": "41",
       "GITHUB_RUN_ATTEMPT": "1", "ARTIFACT_ID": "123", "ACTIONS_ID_TOKEN_REQUEST_URL": "https://oidc/x", "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "r"}


class FakeGitHub:
    def __init__(self, statuses):
        self.statuses, self.calls = list(statuses), []

    def __call__(self, method, url, token=None, body=None, timeout=30):
        self.calls.append((method, url, body))
        if url.startswith("https://oidc"):
            return {"value": "jwt"}
        if method == "GET" and "/git/commits/" in url:
            return {"tree": {"sha": "tree1"}}
        if method == "POST" and url.endswith("/git/commits"):
            assert body["tree"] == "tree1" and body["parents"] == [ENV["GITHUB_SHA"]]
            return {"sha": "c0ffee41"}
        if method == "POST" and url.endswith("/pages/deployments"):
            v = body["pages_build_version"]
            return {"id": v, "status_url": f"https://api.github.com/repos/{ENV['GITHUB_REPOSITORY']}/pages/deployments/{v}",
                    "page_url": "https://darren38.github.io/gso-data-archive/"}
        if method == "GET":
            return {"status": self.statuses.pop(0)}
        return {}


def test_each_run_publishes_under_its_own_commit():
    gh = FakeGitHub(["succeed"])
    dp.deploy(ENV, req=gh, sleep=lambda s: None)
    post = next(c for c in gh.calls if c[0] == "POST" and c[1].endswith("/pages/deployments"))
    assert post[2]["pages_build_version"] == "c0ffee41"  # the bug: every run sent the same commit


def test_waits_for_its_own_deployment():
    gh = FakeGitHub(["deployment_queued", "deployment_in_progress", "succeed"])
    result = dp.deploy(ENV, req=gh, sleep=lambda s: None)
    assert result["status"] == "succeed" and result["page_url"].startswith("https://darren38")
    post = next(c for c in gh.calls if c[0] == "POST" and c[1].endswith("/pages/deployments"))
    assert post[2] == {"artifact_id": 123, "pages_build_version": "c0ffee41", "oidc_token": "jwt"}
    assert all(url.endswith("/c0ffee41") for m, url, _ in gh.calls if m == "GET" and "/pages/" in url)


def test_failure_fails_the_run():
    with pytest.raises(SystemExit, match="Deployment failed"):
        dp.deploy(ENV, req=FakeGitHub(["deployment_failed"]), sleep=lambda s: None)


def test_gives_up_after_the_timeout():
    with pytest.raises(SystemExit, match="did not finish"):
        dp.deploy(ENV, req=FakeGitHub(["deployment_queued"] * 10), sleep=lambda s: None, timeout_s=10, every_s=5)


def test_falls_back_to_the_commit_when_the_version_is_refused():
    import io
    import urllib.error

    gh = FakeGitHub(["succeed"])
    real = gh.__call__

    def refuse_unique(method, url, token=None, body=None, timeout=30):
        if method == "POST" and body and body.get("pages_build_version") == "c0ffee41":
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO(b'{"message":"Not Found"}'))
        return real(method, url, token, body, timeout)

    result = dp.deploy(ENV, req=refuse_unique, sleep=lambda s: None)
    assert result["status"] == "succeed"
    assert [c[2]["pages_build_version"] for c in gh.calls if c[0] == "POST" and c[1].endswith("/pages/deployments")] == ["e32f370c"]


def test_publishes_anyway_when_the_commit_cannot_be_made():
    import io
    import urllib.error

    gh = FakeGitHub(["succeed"])
    real = gh.__call__

    def no_commits(method, url, token=None, body=None, timeout=30):
        if "/git/commits" in url:
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, io.BytesIO(b""))
        return real(method, url, token, body, timeout)

    assert dp.deploy(ENV, req=no_commits, sleep=lambda s: None)["status"] == "succeed"
