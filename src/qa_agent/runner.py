"""Run generated tests with pytest + Playwright and read back what happened."""
from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from .snapshot import SNAPSHOT_JS, format_snapshot

# This conftest is written next to the generated tests. On a failure it saves what the page
# looked like at that moment, so the repair step sees the real DOM rather than guessing.
CONFTEST = '''import json, pathlib
import pytest
from playwright.sync_api import expect

SNAPSHOT_JS = %r
expect.set_options(timeout=4000)


@pytest.fixture(autouse=True)
def _short_timeouts(page):
    page.set_default_timeout(4000)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    yield
    if call.when == "call" and call.excinfo is not None and "page" in item.funcargs:
        page = item.funcargs["page"]
        out = pathlib.Path(__file__).parent / ".snapshots"
        out.mkdir(exist_ok=True)
        try:
            data = {"url": page.url, "elements": page.evaluate(SNAPSHOT_JS)}
            page.screenshot(path=str(out / (item.name + ".png")))
        except Exception as exc:
            data = {"url": "", "elements": [], "error": str(exc)}
        (out / (item.name + ".json")).write_text(json.dumps(data), encoding="utf-8")
''' % SNAPSHOT_JS


def _result(name: str, status: str, message: str = "", page_at_failure: str = "", screenshot: str = "") -> dict:
    """status is one of: passed | failed | xfailed (expected failure = suspected app bug)."""
    return {"name": name, "status": status, "message": message,
            "page_at_failure": page_at_failure, "screenshot": screenshot}


def run_tests(test_code: str, base_url: str, workdir: Path) -> list[dict]:
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "conftest.py").write_text(CONFTEST, encoding="utf-8")
    (workdir / "test_generated.py").write_text(test_code, encoding="utf-8")
    snaps = workdir / ".snapshots"
    if snaps.exists():
        for old in snaps.iterdir():
            old.unlink()
    junit = workdir / "junit.xml"
    junit.unlink(missing_ok=True)

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "test_generated.py", "-q", "-p", "no:cacheprovider",
         "--base-url", base_url, f"--junitxml={junit.name}", "--tb=short"],
        cwd=workdir, capture_output=True, text=True, timeout=600,
    )
    output_tail = (proc.stdout + proc.stderr)[-3000:]
    if not junit.exists():  # pytest could not even start
        return [_result("collection", "failed", output_tail)]

    results = []
    for case in ET.parse(junit).getroot().iter("testcase"):
        raw_name = case.get("name", "?")
        name = raw_name.split("[")[0]  # drop pytest-playwright's "[chromium]" suffix
        failure = case.find("failure")
        if failure is None:
            failure = case.find("error")  # e.g. a syntax error in the generated file
        skipped = case.find("skipped")
        page, shot = "", ""
        snap = snaps / f"{raw_name}.json"
        if snap.exists():
            data = json.loads(snap.read_text(encoding="utf-8"))
            page = format_snapshot(data.get("url", ""), data.get("elements", []))
        if (snaps / f"{raw_name}.png").exists():
            shot = str(snaps / f"{raw_name}.png")
        if failure is not None:
            msg = (failure.get("message") or "") + "\n" + (failure.text or "")
            results.append(_result(name, "failed", msg.strip()[-2500:], page, shot))
        elif skipped is not None:
            results.append(_result(name, "xfailed", skipped.get("message") or "", page, shot))
        else:
            results.append(_result(name, "passed"))
    return results or [_result("collection", "failed", output_tail)]
