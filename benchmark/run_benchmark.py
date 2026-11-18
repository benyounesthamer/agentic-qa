"""Measure the agent instead of trusting a single demo.

Scenarios:
  write/clean          no defect: the agent must end green and must NOT report a bug (false-alarm check)
  write/<bug>          one planted defect: the agent must report it as a suspected app bug
  heal/redesign        tests written for UI v1 are run against UI v2: the agent must get them green again
  heal/redesign+bug    same, with a defect planted: it must heal the selectors AND still report the bug

Usage:  python benchmark/run_benchmark.py            (needs an API key in .env)
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qa_agent.cli import run_agent  # noqa: E402
from qa_agent.graph import test_names  # noqa: E402
from qa_agent.llm import from_env  # noqa: E402
from qa_agent.report import summarize  # noqa: E402

# planted defect -> words that a correct bug report must contain
BUGS = {"counter": ("count",), "empty": ("empty", "blank"), "login": ("password", "login", "credential"),
        "delete": ("delet", "remov")}


def start_app(**env) -> tuple[subprocess.Popen, str]:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, "-m", "demo_app", "--port", str(port)],
                            cwd=ROOT, env={**os.environ, **env})
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            httpx.get(url, timeout=1)
            return proc, url
        except httpx.HTTPError:
            time.sleep(0.2)
    proc.kill()
    raise RuntimeError("demo app did not start")


def scenario(name: str, bug: str | None, llm, story: str, out: Path, env: dict, test_code: str | None = None) -> dict:
    proc, url = start_app(**env)
    calls_before, t0 = llm.calls, time.time()
    try:
        final = run_agent(llm, story, url, out / name.replace("/", "_").replace("+", "_"), test_code=test_code,
                          verbose=False)
        counts = summarize(final["results"])
        reports = [r["message"].lower() for r in final["results"] if r["status"] == "xfailed"]
        right = [m for m in reports if bug and any(word in m for word in BUGS[bug])]
        false_reports = len(reports) - len(right)
        tests_kept = len(final["results"]) >= len(test_names(final["history"][0]["code"]))
        correct = (counts["failed"] == 0 and false_reports == 0 and tests_kept
                   and (len(right) > 0 if bug else True))
        row = {"scenario": name, "expected": f"report the {bug} bug" if bug else "all green, no bug reported",
               **counts, "right_bug": len(right) > 0, "false_reports": false_reports, "tests_kept": tests_kept,
               "repairs": final["repairs"], "llm_calls": llm.calls - calls_before,
               "seconds": round(time.time() - t0), "correct": correct, "test_code": final["test_code"]}
    except Exception as exc:  # a crashed scenario is a failed scenario, not a crashed benchmark
        row = {"scenario": name, "expected": "", "passed": 0, "failed": 0, "xfailed": 0, "repairs": 0,
               "llm_calls": llm.calls - calls_before, "seconds": round(time.time() - t0), "correct": False,
               "right_bug": False, "false_reports": 0, "tests_kept": False, "test_code": "", "error": str(exc)[:300]}
    finally:
        proc.kill()
    print(f"{'OK  ' if row['correct'] else 'MISS'} {name}: {row['passed']} passed, {row['failed']} failed, "
          f"{row['xfailed']} bug(s), {row['repairs']} repair(s), {row['seconds']}s {row.get('error', '')}", flush=True)
    return row


def main() -> None:
    load_dotenv(ROOT / ".env")
    llm = from_env()
    story = (ROOT / "examples" / "story.md").read_text(encoding="utf-8")
    out = ROOT / "benchmark" / "runs"
    rows = [scenario("write/clean", None, llm, story, out, {})]
    for bug in BUGS:
        rows.append(scenario(f"write/{bug}", bug, llm, story, out, {"DEMO_BUG": bug}))

    baseline = rows[0]  # the suite written for UI v1 with no defect
    if baseline["correct"]:
        v2 = {"DEMO_UI_VERSION": "2"}
        rows.append(scenario("heal/redesign", None, llm, story, out, v2, baseline["test_code"]))
        rows.append(scenario("heal/redesign+counter", "counter", llm, story, out, {**v2, "DEMO_BUG": "counter"},
                             baseline["test_code"]))
    else:
        print("Skipping heal scenarios: the clean baseline suite was not green.")

    correct = sum(r["correct"] for r in rows)
    md = [f"# Benchmark results", "", f"Model: `{llm.model}` · {time.strftime('%Y-%m-%d')} · one run per scenario", "",
          f"**{correct} of {len(rows)} scenarios correct.**", "",
          "A scenario is correct when no test is left failing, the planted bug (if any) is the one reported,",
          "nothing else is reported as a bug, and no test was deleted along the way.", "",
          "| Scenario | Expected | Passed | Failed | Bugs reported | False reports | Repairs | LLM calls | Time | Correct |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['scenario']} | {r['expected']} | {r['passed']} | {r['failed']} | {r['xfailed']} | {r['false_reports']} | "
                  f"{r['repairs']} | {r['llm_calls']} | {r['seconds']}s | {'yes' if r['correct'] else 'NO'} |")
    (ROOT / "benchmark" / "results.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (ROOT / "benchmark" / "results.json").write_text(
        json.dumps([{k: v for k, v in r.items() if k != "test_code"} for r in rows], indent=2), encoding="utf-8")
    print(f"\n{correct}/{len(rows)} correct. See benchmark/results.md")


if __name__ == "__main__":
    main()
