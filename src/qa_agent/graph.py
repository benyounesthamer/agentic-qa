"""The agent: explore -> plan -> write -> run -> (repair -> run)* -> report.

In "heal" mode an existing test file is given, so planning and writing are skipped.

Each step is a small function that reads the shared state and returns the keys it changed.
LangGraph wires them together and decides, after every test run, whether to repair or stop.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from . import prompts
from .report import render_html, render_markdown, summarize
from .llm import LLM
from .runner import run_tests
from .snapshot import explore


class QAState(TypedDict, total=False):
    story: str            # the user story to verify
    base_url: str         # where the app under test is running
    workdir: str          # folder for generated tests and the report
    max_repairs: int
    max_explore: int      # how many exploration rounds the agent may use
    page_snapshot: str    # description of every page the agent found
    pages_found: list[str]
    plan: list[dict]      # test cases the agent decided to write
    test_code: str        # current version of the generated test file
    results: list[dict]   # outcome of the latest run
    repairs: int          # how many repair rounds have happened
    history: list[dict]   # one entry per run: counts, diagnoses and the code that ran
    report_path: str


def _compiles(code: str) -> bool:
    try:
        compile(code, "test_generated.py", "exec")
        return True
    except SyntaxError:
        return False


def extract_code(text: str, fallback: str | None = None) -> str:
    """Pull the Python file out of a model reply.

    Fences are read line by line (a regex gets confused when a reply has several blocks).
    We take the longest block that is valid Python; if nothing is valid, keep `fallback`.
    """
    blocks, current = [], None
    for line in text.splitlines():
        if line.strip().startswith("```"):
            if current is None:
                current = []
            else:
                blocks.append("\n".join(current))
                current = None
        elif current is not None:
            current.append(line)
    if current:  # reply was cut off before the closing fence
        blocks.append("\n".join(current))
    valid = [b for b in blocks or [text] if b.strip() and _compiles(b)]
    if valid:
        return max(valid, key=len).strip() + "\n"
    return fallback if fallback is not None else (max(blocks, key=len) if blocks else text).strip() + "\n"


def test_names(code: str) -> set[str]:
    return set(re.findall(r"^def (test_\w+)", code, flags=re.M))


def extract_json(text: str):
    """Pull the first JSON array or object out of a model reply."""
    fenced = re.search(r"```(?:json)?\s*\n(.*?)```", text, flags=re.S)
    candidates = [fenced.group(1)] if fenced else []
    for opener, closer in ("[", "]"), ("{", "}"):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            candidates.append(text[start:end + 1])
    for c in candidates:
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            continue
    return None


def build_graph(llm: LLM):
    def explore_app(state: QAState) -> dict:
        """Let the model drive the browser to find the pages the story talks about."""
        pages, _ = explore(state["base_url"])
        actions, error = [], ""
        for _ in range(state.get("max_explore", 3)):
            reply = llm.complete(prompts.EXPLORE_SYSTEM, prompts.EXPLORE_USER.format(
                story=state["story"], pages="\n\n".join(pages.values()),
                actions=json.dumps(actions), error=error or "none"))
            proposed = extract_json(reply)
            if not isinstance(proposed, list) or not proposed:
                break  # the model says it has seen enough
            actions = proposed
            found, error = explore(state["base_url"], actions)
            pages.update(found)
        return {"page_snapshot": "\n\n".join(pages.values()), "pages_found": list(pages),
                "repairs": 0, "history": [], "plan": state.get("plan", [])}

    def plan_tests(state: QAState) -> dict:
        reply = llm.complete(prompts.PLAN_SYSTEM,
                             prompts.PLAN_USER.format(story=state["story"], snapshot=state["page_snapshot"]))
        plan = extract_json(reply)
        if not isinstance(plan, list):
            plan = [{"id": "TC1", "title": "Cover the user story", "steps": state["story"], "expected": ""}]
        return {"plan": plan}

    def write_tests(state: QAState) -> dict:
        reply = llm.complete(prompts.WRITE_SYSTEM, prompts.WRITE_USER.format(
            story=state["story"], plan=json.dumps(state["plan"], indent=2), snapshot=state["page_snapshot"]))
        return {"test_code": extract_code(reply)}

    def execute_tests(state: QAState) -> dict:
        results = run_tests(state["test_code"], state["base_url"], Path(state["workdir"]))
        entry = {"run": len(state["history"]) + 1, **summarize(results), "diagnoses": [],
                 "code": state["test_code"]}
        return {"results": results, "history": state["history"] + [entry]}

    def repair_tests(state: QAState) -> dict:
        failures = "\n\n".join(
            f"### {r['name']}\n{r['message']}\n\nPage when it failed:\n{r['page_at_failure'] or '(not captured)'}"
            for r in state["results"] if r["status"] == "failed")
        reply = llm.complete(prompts.REPAIR_SYSTEM, prompts.REPAIR_USER.format(
            story=state["story"], code=state["test_code"], failures=failures,
            previous=json.dumps([d for h in state["history"] for d in h["diagnoses"]], indent=1)))
        diagnoses = extract_json(reply.split("```python")[0])
        if isinstance(diagnoses, dict):
            diagnoses = [diagnoses]
        history = state["history"][:-1] + [{**state["history"][-1], "diagnoses": diagnoses or []}]
        new_code = extract_code(reply, fallback=state["test_code"])
        dropped = test_names(state["test_code"]) - test_names(new_code)
        if dropped:  # guard: a repair that deletes tests is rejected, the previous file is kept
            new_code = state["test_code"]
            history[-1]["diagnoses"] = history[-1]["diagnoses"] + [{
                "test": ", ".join(sorted(dropped)), "cause": "rejected_repair",
                "explanation": "The proposed repair deleted these tests, so it was discarded."}]
        return {"test_code": new_code, "repairs": state["repairs"] + 1, "history": history}

    def write_report(state: QAState) -> dict:
        out = Path(state["workdir"])
        (out / "report.md").write_text(render_markdown(state), encoding="utf-8")
        (out / "report.html").write_text(render_html(state), encoding="utf-8")
        # keep the full state, so the reports can be re-rendered later without calling the model
        (out / "state.json").write_text(json.dumps(state, indent=1, default=str), encoding="utf-8")
        return {"report_path": str(out / "report.html")}

    def after_explore(state: QAState) -> str:
        return "execute_tests" if state.get("test_code") else "plan_tests"  # heal mode skips writing

    def after_run(state: QAState) -> str:
        failed = any(r["status"] == "failed" for r in state["results"])
        return "repair_tests" if failed and state["repairs"] < state.get("max_repairs", 3) else "write_report"

    g = StateGraph(QAState)
    for fn in (explore_app, plan_tests, write_tests, execute_tests, repair_tests, write_report):
        g.add_node(fn.__name__, fn)
    g.add_edge(START, "explore_app")
    g.add_conditional_edges("explore_app", after_explore, ["plan_tests", "execute_tests"])
    g.add_edge("plan_tests", "write_tests")
    g.add_edge("write_tests", "execute_tests")
    g.add_conditional_edges("execute_tests", after_run, ["repair_tests", "write_report"])
    g.add_edge("repair_tests", "execute_tests")
    g.add_edge("write_report", END)
    return g.compile()
