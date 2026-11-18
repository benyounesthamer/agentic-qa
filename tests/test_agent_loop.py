"""End-to-end check of the agent loop without a real model.

A scripted fake LLM plays the model's part, but everything else is real: the demo app runs,
a real browser executes the generated tests, and the graph must route failure -> repair -> pass.
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from qa_agent.graph import build_graph, extract_code, extract_json

ROOT = Path(__file__).resolve().parents[1]

NO_EXPLORE = "[]"  # the model says: nothing more to explore
LOGIN_STEPS = ('[{"action": "fill", "selector": "#username", "value": "demo"},'
               ' {"action": "fill", "selector": "#password", "value": "demo123"},'
               ' {"action": "click", "selector": "#login-btn"}]')
PLAN = '[{"id": "TC1", "title": "Valid login", "steps": "log in", "expected": "task page opens"}]'

BROKEN = '''```python
from playwright.sync_api import expect

def test_valid_login(page, base_url):
    page.goto(base_url)
    page.locator("#user").fill("demo")          # wrong id on purpose
    page.locator("#password").fill("demo123")
    page.get_by_role("button", name="Log in").click()
    expect(page).to_have_url(base_url + "/todos")

def test_delete_decreases_counter(page, base_url):
    page.goto(base_url + "/todos")
    page.get_by_placeholder("What needs to be done?").fill("Buy milk")
    page.get_by_role("button", name="Add").click()
    page.get_by_role("button", name="Delete Buy milk").click()
    expect(page.locator("#count")).to_have_text("0")
```'''

FIXED_LOGIN = BROKEN.replace('"#user"', '"#username"').replace("          # wrong id on purpose", "")
REPAIR_SELECTOR = '[{"test": "test_valid_login", "cause": "selector", "explanation": "id is #username"}]\n' + FIXED_LOGIN
REPAIR_APP_BUG = (
    '[{"test": "test_delete_decreases_counter", "cause": "app_bug", "explanation": "counter stays at 1"}]\n'
    + FIXED_LOGIN.replace("from playwright.sync_api import expect", "import pytest\nfrom playwright.sync_api import expect")
    .replace("def test_delete_decreases_counter",
             '@pytest.mark.xfail(reason="APP BUG: counter not decremented on delete", strict=True)\n'
             "def test_delete_decreases_counter"))


class FakeLLM:
    def __init__(self, replies):
        self.replies, self.prompts = list(replies), []

    def complete(self, system, user):
        self.prompts.append(user)
        return self.replies.pop(0)


def start_app(**env):
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


@pytest.fixture
def app(request):
    proc, url = start_app(**getattr(request, "param", {}))
    yield url
    proc.kill()


def run_agent(url, tmp_path, replies, **extra):
    llm = FakeLLM(replies)
    final = build_graph(llm).invoke({"story": "Users can log in and manage tasks.", "base_url": url,
                                     "workdir": str(tmp_path), "max_repairs": 3, **extra})
    return final, llm


def test_broken_selector_is_repaired(app, tmp_path):
    final, llm = run_agent(app, tmp_path, [NO_EXPLORE, PLAN, BROKEN, REPAIR_SELECTOR])
    assert [r["status"] for r in final["results"]] == ["passed", "passed"]
    assert final["repairs"] == 1
    assert [h["failed"] for h in final["history"]] == [1, 0]
    # the repair prompt must contain the real page, so the model can see the correct id
    assert 'id="username"' in llm.prompts[-1]
    assert "selector" in (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "#username" in (tmp_path / "report.html").read_text(encoding="utf-8")  # the diff shows the fix


@pytest.mark.parametrize("app", [{"DEMO_BUG": "1"}], indirect=True)
def test_app_bug_is_reported_not_hidden(app, tmp_path):
    final, _ = run_agent(app, tmp_path, [NO_EXPLORE, PLAN, FIXED_LOGIN, REPAIR_APP_BUG])
    assert {r["name"]: r["status"] for r in final["results"]} == {
        "test_valid_login": "passed", "test_delete_decreases_counter": "xfailed"}
    assert "1 suspected app bug" in (tmp_path / "report.md").read_text(encoding="utf-8")
    bug = [r for r in final["results"] if r["status"] == "xfailed"][0]
    assert Path(bug["screenshot"]).exists()  # evidence is kept
    assert "data:image/png;base64" in (tmp_path / "report.html").read_text(encoding="utf-8")


def test_exploration_reaches_pages_behind_login(app, tmp_path):
    final, llm = run_agent(app, tmp_path, [LOGIN_STEPS, NO_EXPLORE, PLAN, FIXED_LOGIN])
    assert any(u.endswith("/todos") for u in final["pages_found"])
    assert 'id="new-todo"' in final["page_snapshot"]  # the task page is known before any test is written
    assert final["repairs"] == 0


@pytest.mark.parametrize("app", [{"DEMO_UI_VERSION": "2"}], indirect=True)
def test_heal_mode_repairs_existing_suite_after_redesign(app, tmp_path):
    old_suite = FIXED_LOGIN.split("```python\n")[1].split("```")[0]  # written for UI v1
    healed = (old_suite.replace("#username", "#user-input").replace("#password", "#pass-input")
              .replace('name="Log in"', 'name="Sign in"').replace('name="Add"', 'name="Create task"')
              .replace("#count", "#remaining"))
    repair = '[{"test": "all", "cause": "selector", "explanation": "ids renamed"}]\n```python\n' + healed + "```"
    final, llm = run_agent(app, tmp_path, [NO_EXPLORE, repair], test_code=old_suite)
    assert [h["failed"] for h in final["history"]] == [2, 0]
    assert len(llm.prompts) == 2  # explore + repair only: no planning or writing in heal mode


def test_gives_up_after_max_repairs(app, tmp_path):
    final, _ = run_agent(app, tmp_path, [NO_EXPLORE, PLAN, BROKEN, BROKEN, BROKEN, BROKEN])
    assert final["repairs"] == 3
    assert any(r["status"] == "failed" for r in final["results"])


def test_parsers():
    assert extract_code("text\n```python\nx = 1\n```\nmore") == "x = 1\n"
    # a reply with a JSON block, a heading, then the code: the code must win, not the heading
    reply = '```json\n[{"test": "t"}]\n```\n**2. Corrected test file**\n```python\ndef test_a():\n    pass\n```'
    assert extract_code(reply) == "def test_a():\n    pass\n"
    assert extract_code("```python\ndef broken(:\n```", fallback="keep\n") == "keep\n"
    assert extract_json('Here you go:\n[{"a": 1}]\n```python\nd = {}\n```') == [{"a": 1}]
    assert extract_json("no json here") is None
