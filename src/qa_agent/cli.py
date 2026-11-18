"""Command line.

Write tests from a story:   qa-agent --url http://127.0.0.1:8000 --story examples/story.md
Heal an existing suite:     qa-agent --url http://127.0.0.1:8000 --story examples/story.md --tests old_tests.py
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from .graph import build_graph
from .llm import LLM, from_env


def run_agent(llm: LLM, story: str, url: str, workdir: Path, max_repairs: int = 3,
              test_code: str | None = None, verbose: bool = True) -> dict:
    """Run the whole graph and return the final state. Shared by the CLI and the benchmark."""
    state = {"story": story, "base_url": url, "workdir": str(workdir.resolve()), "max_repairs": max_repairs}
    if test_code:
        state["test_code"] = test_code
    for step in build_graph(llm).stream(state, stream_mode="updates"):
        for node, update in step.items():
            state = {**state, **(update or {})}
            if not verbose:
                continue
            line = f"[{node}]"
            if node == "explore_app":
                line += f" found {len(state['pages_found'])} page(s): {', '.join(state['pages_found'])}"
            if node == "execute_tests":
                h = state["history"][-1]
                line += f" run {h['run']}: {h['passed']} passed, {h['failed']} failed, {h['xfailed']} suspected bug(s)"
            print(line, flush=True)
    return state


def main() -> None:
    p = argparse.ArgumentParser(description="Write, run and repair Playwright tests from a user story.")
    p.add_argument("--url", required=True, help="Base URL of the application under test")
    p.add_argument("--story", required=True, type=Path, help="Markdown file containing the user story")
    p.add_argument("--tests", type=Path, help="Heal mode: start from this existing test file")
    p.add_argument("--out", type=Path, default=Path("runs"), help="Folder for generated tests and reports")
    p.add_argument("--max-repairs", type=int, default=3)
    args = p.parse_args()

    load_dotenv(".env")
    workdir = args.out / datetime.now().strftime("%Y%m%d-%H%M%S")
    final = run_agent(from_env(), args.story.read_text(encoding="utf-8"), args.url, workdir, args.max_repairs,
                      args.tests.read_text(encoding="utf-8") if args.tests else None)

    print(f"\nReport: {final['report_path']}")
    print(f"Tests:  {workdir.resolve() / 'test_generated.py'}")
    sys.exit(1 if any(r["status"] == "failed" for r in final["results"]) else 0)


if __name__ == "__main__":
    main()
