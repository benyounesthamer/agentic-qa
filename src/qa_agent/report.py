"""Reports: a Markdown summary and a self-contained HTML page with screenshots and a code diff."""
from __future__ import annotations

import base64
import difflib
from html import escape
import re
from pathlib import Path


def plan_coverage(plan: list[dict], code: str) -> tuple[int, list[str]]:
    """How many test cases of the plan have a test named after their id (test_tc04_...)."""
    names = [n.lower() for n in re.findall(r"^def (test_\w+)", code, flags=re.M)]

    def has_test(plan_id: str) -> bool:
        # "TC4", "TC-04" and "tc04" are the same case: compare the prefix and the number, not the text
        m = re.fullmatch(r"([a-z]*)[\s_-]*0*(\d+)", plan_id.lower().strip())
        if not m:
            return any(plan_id.lower() in n for n in names)
        pattern = re.compile(rf"^test_{m.group(1)}_?0*{m.group(2)}(_|$)")
        return any(pattern.match(n) for n in names)

    missing = [str(tc.get("id", "")) for tc in plan if tc.get("id") and not has_test(str(tc["id"]))]
    return len(plan) - len(missing), missing


def summarize(results: list[dict]) -> dict:
    return {s: sum(r["status"] == s for r in results) for s in ("passed", "failed", "xfailed")}


def _diagnoses(state: dict) -> list[tuple[int, dict]]:
    return [(h["run"], d) for h in state["history"] for d in h["diagnoses"] if isinstance(d, dict)]


def _short_error(message: str) -> str:
    """The assertion and its first lines, not the full page dump Playwright appends."""
    lines = [ln for ln in message.splitlines() if ln.strip() and not ln.lstrip("E ").startswith("- ")]
    return "\n".join(lines[:8])[:700]


def _first_line(message: str) -> str:
    return message.splitlines()[0] if message else ""


def _story_title(story: str) -> str:
    """First meaningful line of the story, without Markdown heading marks."""
    for line in story.splitlines():
        if line.strip():
            return line.strip().lstrip("#").strip()
    return ""


def render_markdown(state: dict) -> str:
    final = summarize(state["results"])
    out = ["# QA agent report", "", f"Target: {state['base_url']}", "",
           f"**Final result: {final['passed']} passed, {final['failed']} failed, "
           f"{final['xfailed']} suspected app bug(s)** after {state['repairs']} repair round(s).", "",
           f"Pages explored: {', '.join(state.get('pages_found', []))}", ""]
    if state.get("plan"):
        covered, missing = plan_coverage(state["plan"], state["test_code"])
        out += [f"Plan coverage: {covered} of {len(state['plan'])} test cases have a test"
                + (f" (missing: {', '.join(missing)})" if missing else "") + ".", ""]
    if state.get("plan"):
        out += ["## Test plan", "", "| ID | Title | Expected |", "|---|---|---|"]
        out += [f"| {tc.get('id', '')} | {tc.get('title', '')} | {tc.get('expected', '')} |" for tc in state["plan"]]
        out.append("")
    out += ["## Runs", "", "| Run | Passed | Failed | Suspected bugs |", "|---|---|---|---|"]
    out += [f"| {h['run']} | {h['passed']} | {h['failed']} | {h['xfailed']} |" for h in state["history"]]
    if _diagnoses(state):
        out += ["", "## What the agent diagnosed", "", "| After run | Test | Cause | Explanation |", "|---|---|---|---|"]
        out += [f"| {run} | {d.get('test', '')} | {d.get('cause', '')} | {d.get('explanation', '')} |"
                for run, d in _diagnoses(state)]
    out += ["", "## Final status per test", ""]
    for r in state["results"]:
        note = f" - {_first_line(r['message'])}" if r["status"] != "passed" else ""
        out.append(f"- `{r['name']}`: **{r['status']}**{note}")
    return "\n".join(out) + "\n"


CSS = """
:root { --bg:#f7f7f5; --card:#fff; --text:#1c1c1a; --muted:#6b6b66; --line:#e3e3de;
        --pass:#1f8a4c; --fail:#c0392b; --bug:#b7791f; --add:#e6f4ea; --del:#fdeaea; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#161615; --card:#1f1f1d; --text:#ececE8; --muted:#9a9a93; --line:#33332f;
          --pass:#4cc38a; --fail:#ff7b6b; --bug:#e5b454; --add:#16301f; --del:#3a1c1c; } }
* { box-sizing: border-box; }
body { margin:0; padding:32px 16px; background:var(--bg); color:var(--text);
       font:15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 980px; margin: 0 auto; }
h1 { font-size: 26px; margin: 0 0 4px; } h2 { font-size: 18px; margin: 36px 0 12px; }
.muted { color: var(--muted); } code, pre { font-family: ui-monospace, Consolas, monospace; font-size: 13px; }
.tiles { display:grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap:12px; margin:20px 0; }
.tile, .card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; }
.tile b { display:block; font-size:28px; line-height:1.1; } .pass { color:var(--pass); } .fail { color:var(--fail); }
.bug { color:var(--bug); }
.run { display:grid; grid-template-columns: 60px 1fr 220px; gap:12px; align-items:center; margin:8px 0; }
.bar { display:flex; height:18px; border-radius:6px; overflow:hidden; background:var(--line); }
.bar i { display:block; height:100%; } .bar .p { background:var(--pass); } .bar .f { background:var(--fail); }
.bar .b { background:var(--bug); }
table { width:100%; border-collapse:collapse; background:var(--card); border:1px solid var(--line); border-radius:10px; }
th, td { text-align:left; padding:8px 12px; border-bottom:1px solid var(--line); vertical-align:top; }
th { font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }
.tag { display:inline-block; padding:1px 8px; border-radius:99px; border:1px solid currentColor; font-size:12px; }
.card { margin:12px 0; } .card p { margin:8px 0; }
.card img { display:block; width:100%; height:230px; object-fit:cover; object-position:top center; background:#fff;
            border:1px solid var(--line); border-radius:8px; margin-top:10px; }
.bugs { display:grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap:12px; }
.bugs .card { margin:0; } .why { color:var(--muted); font-size:14px; }
.why b { color:var(--text); font-weight:600; }
pre { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px; overflow-x:auto; margin:0; }
pre .a { background:var(--add); display:block; } pre .d { background:var(--del); display:block; }
"""


def _image(path: str) -> str:
    if not path or not Path(path).exists():
        return ""
    data = base64.b64encode(Path(path).read_bytes()).decode()
    return f'<img alt="Screenshot at the moment of failure" src="data:image/png;base64,{data}">'


def _diff(before: str, after: str) -> str:
    lines = []
    for line in difflib.unified_diff(before.splitlines(), after.splitlines(), "first version", "final version",
                                     lineterm="", n=2):
        cls = "a" if line.startswith("+") and not line.startswith("+++") else \
              "d" if line.startswith("-") and not line.startswith("---") else ""
        lines.append(f'<span class="{cls}">{escape(line) or " "}</span>' if cls else escape(line) + "\n")
    return "".join(lines) or "No changes: the first version was already correct."


def render_html(state: dict) -> str:
    final = summarize(state["results"])
    e = escape
    h = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
         f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
         f"<title>QA agent report</title><style>{CSS}</style></head><body><main>",
         "<h1>QA agent report</h1>",
         f"<p>{e(_story_title(state.get('story', '')))}</p>",
         f"<div class='muted'>Target {e(state['base_url'])} · {len(state.get('pages_found', []))} page(s) explored · "
         f"{state['repairs']} repair round(s)</div>",
         "<div class='tiles'>",
         f"<div class='tile'><b class='pass'>{final['passed']}</b>tests passing</div>",
         f"<div class='tile'><b class='bug'>{final['xfailed']}</b>suspected app bugs</div>",
         f"<div class='tile'><b class='fail'>{final['failed']}</b>tests still failing</div>",
         f"<div class='tile'><b>{len(state['history'])}</b>test runs</div>"]
    if state.get("plan"):
        covered, _ = plan_coverage(state["plan"], state["test_code"])
        h.append(f"<div class='tile'><b>{covered}/{len(state['plan'])}</b>plan cases covered</div>")
    h.append("</div>")

    h.append("<h2>How the suite improved, run by run</h2>")
    for r in state["history"]:
        total = max(r["passed"] + r["failed"] + r["xfailed"], 1)
        h.append(f"<div class='run'><span>Run {r['run']}</span><div class='bar'>"
                 f"<i class='p' style='width:{100 * r['passed'] / total}%'></i>"
                 f"<i class='b' style='width:{100 * r['xfailed'] / total}%'></i>"
                 f"<i class='f' style='width:{100 * r['failed'] / total}%'></i></div>"
                 f"<span class='muted'>{r['passed']} passed · {r['xfailed']} bug · {r['failed']} failed</span></div>")

    bugs = [r for r in state["results"] if r["status"] == "xfailed"]
    if bugs:
        # the agent's own reasoning for each accusation, so a reviewer can judge it
        why = {d.get("test"): d.get("explanation", "") for _, d in _diagnoses(state) if d.get("cause") == "app_bug"}
        h.append("<h2>Suspected application bugs</h2><div class='bugs'>")
        for r in bugs:
            title = _first_line(r["message"]).replace("reason: ", "").replace("APP BUG: ", "")
            reason = f"<p class='why'><b>Agent's reasoning:</b> {e(why[r['name']])}</p>" if why.get(r["name"]) else ""
            h.append(f"<div class='card'><span class='tag bug'>app bug</span> <code>{e(r['name'])}</code>"
                     f"<p><b>{e(title)}</b></p>{reason}{_image(r.get('screenshot', ''))}</div>")
        h.append("</div>")

    still = [r for r in state["results"] if r["status"] == "failed"]
    if still:
        h.append("<h2>Tests the agent could not fix</h2>")
        for r in still:
            h.append(f"<div class='card'><span class='tag fail'>failed</span> <code>{e(r['name'])}</code>"
                     f"<pre>{e(_short_error(r['message']))}</pre>{_image(r.get('screenshot', ''))}</div>")

    if _diagnoses(state):
        h.append("<h2>What the agent diagnosed</h2><table><tr><th>After run</th><th>Test</th><th>Cause</th>"
                 "<th>Explanation</th></tr>")
        for run, d in _diagnoses(state):
            cause = str(d.get("cause", ""))
            cls = "bug" if cause == "app_bug" else "muted"
            h.append(f"<tr><td>{run}</td><td><code>{e(str(d.get('test', '')))}</code></td>"
                     f"<td><span class='tag {cls}'>{e(cause)}</span></td><td>{e(str(d.get('explanation', '')))}</td></tr>")
        h.append("</table>")

    if state.get("plan"):
        h.append("<h2>Test plan</h2><table><tr><th>ID</th><th>Title</th><th>Expected</th></tr>")
        for tc in state["plan"]:
            h.append(f"<tr><td>{e(str(tc.get('id', '')))}</td><td>{e(str(tc.get('title', '')))}</td>"
                     f"<td>{e(str(tc.get('expected', '')))}</td></tr>")
        h.append("</table>")

    h.append("<h2>What the agent changed in the tests</h2>")
    h.append(f"<pre>{_diff(state['history'][0]['code'], state['test_code'])}</pre>")
    h.append("</main></body></html>")
    return "\n".join(h)
