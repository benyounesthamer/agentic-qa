"""Measure the agent on the NovaBank demo app instead of trusting a single demo.

Scenarios:
  clean              no defect: the agent must end green and must NOT report a bug (false-alarm check)
  <bug>              one planted defect (9 of them): the agent must report that defect, and nothing else
  heal               the clean scenario's tests are run against the redesigned UI: they must be healed to green

Resumable: each finished scenario is saved to benchmark/results.jsonl, and a re-run skips the scenarios
already done with the same model. On a free API tier the daily token quota allows only a few scenarios
per day, so the benchmark is meant to be run again until every scenario is done.

Usage:  python benchmark/run_benchmark.py [scenario ...]     (needs an API key in .env)
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
sys.path.insert(0, str(ROOT))

from demo_bank.app import BUGS  # noqa: E402
from qa_agent.cli import run_agent  # noqa: E402
from qa_agent.graph import test_names  # noqa: E402
from qa_agent.llm import from_env  # noqa: E402
from qa_agent.report import plan_coverage, summarize  # noqa: E402

# planted defect -> words a correct bug report must contain (any of them)
KEYWORDS = {
    "limit": ("limit",), "negative": ("negative", "zero", "greater than"),
    "overdraft": ("balance", "insufficient", "overdraft", "exceed"), "balance": ("balance", "debit"),
    "rounding": ("balance", "exact", "round", "decimal", "millime", "debit"), "iban": ("iban", "check digit"),
    "delete": ("delet", "remov"), "statement": ("statement",), "logout": ("logout", "log out", "session"),
}
STORY = (ROOT / "examples" / "bank_story.md").read_text(encoding="utf-8")
OUT = ROOT / "benchmark" / "results.jsonl"


def start_app(**env) -> tuple[subprocess.Popen, str]:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, "-m", "demo_bank", "--port", str(port)],
                            cwd=ROOT, env={**os.environ, "DEMO_BUG": "", "DEMO_UI_VERSION": "1", **env})
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            httpx.get(url + "/login", timeout=1)
            return proc, url
        except httpx.HTTPError:
            time.sleep(0.2)
    proc.kill()
    raise RuntimeError("demo app did not start")


def run_scenario(name: str, llm, env: dict, bug: str | None, test_code: str | None = None) -> dict:
    proc, url = start_app(**env)
    calls, t0 = llm.calls, time.time()
    try:
        final = run_agent(llm, STORY, url, ROOT / "benchmark" / "runs" / name, test_code=test_code, verbose=False)
        counts = summarize(final["results"])
        reports = [r["message"].lower() for r in final["results"] if r["status"] == "xfailed"]
        right = [m for m in reports if bug and any(w in m for w in KEYWORDS[bug])]
        covered, _ = plan_coverage(final.get("plan") or [], final["test_code"])
        row = {"scenario": name, "expected": f"report the {bug} bug" if bug else "all green, no bug reported",
               **counts, "right_bug": bool(right), "false_reports": len(reports) - len(right),
               "tests": len(test_names(final["test_code"])), "plan": len(final.get("plan") or []),
               "covered": covered, "repairs": final["repairs"],
               "correct": counts["failed"] == 0 and len(reports) == len(right) and (bool(right) if bug else True),
               "test_code": final["test_code"]}
    except Exception as exc:  # a crashed scenario is recorded, not fatal
        row = {"scenario": name, "error": str(exc)[:300], "correct": False}
    finally:
        proc.kill()
    row.update(model=llm.model, llm_calls=llm.calls - calls, seconds=round(time.time() - t0))
    return row


def main() -> None:
    load_dotenv(ROOT / ".env")
    llm = from_env()
    done = {}
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r.get("model") == llm.model and "error" not in r:
                done[r["scenario"]] = r
    wanted = sys.argv[1:] or ["clean", *BUGS, "heal"]

    for name in wanted:
        if name in done:
            continue
        if name == "heal":
            if "clean" not in done or not done["clean"]["correct"]:
                print("heal: needs a correct clean scenario first, skipped")
                continue
            row = run_scenario("heal", llm, {"DEMO_UI_VERSION": "2"}, None, done["clean"]["test_code"])
        else:
            bug = None if name == "clean" else name
            row = run_scenario(name, llm, {"DEMO_BUG": bug or ""}, bug)
        with OUT.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        if "error" not in row:
            done[name] = row
        print(f"{'OK  ' if row['correct'] else 'MISS'} {name}: {row.get('error') or ''}"
              f"{row.get('passed', '')} passed, {row.get('failed', '')} failed, {row.get('xfailed', '')} bug(s), "
              f"{row.get('false_reports', '')} false, {row['llm_calls']} calls, {row['seconds']}s", flush=True)
        if "quota" in row.get("error", "").lower():
            print("Daily quota reached: run the benchmark again later to continue.")
            break
    write_table(done, llm.model)


def write_table(done: dict, model: str) -> None:
    order = ["clean", *BUGS, "heal"]
    rows = [done[s] for s in order if s in done]
    correct = sum(r["correct"] for r in rows)
    md = ["# Benchmark results", "",
          f"App: NovaBank demo · model `{model}` · one run per scenario · {len(rows)} of {len(order)} scenarios done", "",
          f"**{correct} of {len(rows)} completed scenarios correct.** A scenario is correct when no test is left "
          "failing, the planted bug (if any) is reported, nothing else is reported as a bug, and no test was deleted.", "",
          "| Scenario | Planted defect | Tests (plan covered) | Passed | Failed | Bugs reported | False reports | Repairs | LLM calls | Correct |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        defect = BUGS.get(r["scenario"], "none" if r["scenario"] == "clean" else "UI redesign")
        md.append(f"| {r['scenario']} | {defect} | {r['tests']} ({r['covered']}/{r['plan']}) | {r['passed']} | "
                  f"{r['failed']} | {r['xfailed']} | {r['false_reports']} | {r['repairs']} | {r['llm_calls']} | "
                  f"{'yes' if r['correct'] else 'NO'} |")
    (ROOT / "benchmark" / "results.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
