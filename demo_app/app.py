"""Tiny web app used as the system under test.

Two switches let us simulate real-life situations for the agent:
  DEMO_UI_VERSION=2  -> a redesign: ids and button labels change (tests must be repaired)
  DEMO_BUG=<name>    -> a real defect (comma-separated list allowed):
       counter  the counter does not go down when a task is deleted
       empty    an empty task can be added
       login    a wrong password is accepted
       delete   the Delete button does not remove the task
"""
import os

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Demo Todo App")

V1 = dict(user="username", pwd="password", login="login-btn", login_text="Log in",
          new="new-todo", add="add-btn", add_text="Add", count="count")
V2 = dict(user="user-input", pwd="pass-input", login="signin", login_text="Sign in",
          new="task-input", add="task-submit", add_text="Create task", count="remaining")


def bugs() -> set:
    raw = os.getenv("DEMO_BUG", "").replace("1", "counter")
    return {b.strip() for b in raw.split(",") if b.strip()}


def ids() -> dict:
    return V2 if os.getenv("DEMO_UI_VERSION", "1") == "2" else V1


class Credentials(BaseModel):
    username: str
    password: str


@app.post("/api/login")
def login(c: Credentials):
    if c.username == "demo" and (c.password == "demo123" or "login" in bugs()):
        return {"ok": True}
    return JSONResponse({"ok": False, "error": "Invalid username or password"}, status_code=401)


@app.get("/", response_class=HTMLResponse)
def login_page():
    i = ids()
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Demo - Login</title></head><body>
<h1>Welcome</h1>
<form id="login-form">
  <label for="{i['user']}">Username</label> <input id="{i['user']}" name="username">
  <label for="{i['pwd']}">Password</label> <input id="{i['pwd']}" name="password" type="password">
  <button id="{i['login']}" type="submit">{i['login_text']}</button>
</form>
<p id="error" role="alert"></p>
<script>
document.getElementById('login-form').addEventListener('submit', async (e) => {{
  e.preventDefault();
  const r = await fetch('/api/login', {{method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{username: document.getElementById('{i['user']}').value,
                          password: document.getElementById('{i['pwd']}').value}})}});
  if (r.ok) {{ window.location = '/todos'; }}
  else {{ document.getElementById('error').textContent = (await r.json()).error; }}
}});
</script></body></html>"""


@app.get("/todos", response_class=HTMLResponse)
def todos_page():
    i = ids()
    b = bugs()
    bug_counter, bug_empty, bug_delete = ("true" if x in b else "false" for x in ("counter", "empty", "delete"))
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Demo - Tasks</title></head><body>
<h1>My tasks</h1>
<input id="{i['new']}" placeholder="What needs to be done?">
<button id="{i['add']}">{i['add_text']}</button>
<ul id="todo-list"></ul>
<p><span id="{i['count']}">0</span> tasks</p>
<script>
const BUG_COUNTER = {bug_counter}, BUG_EMPTY = {bug_empty}, BUG_DELETE = {bug_delete};
let n = 0;
const count = document.getElementById('{i['count']}');
document.getElementById('{i['add']}').addEventListener('click', () => {{
  const input = document.getElementById('{i['new']}');
  const text = input.value.trim();
  if (!text && !BUG_EMPTY) return;
  const li = document.createElement('li');
  const span = document.createElement('span'); span.textContent = text;
  const del = document.createElement('button'); del.textContent = 'Delete';
  del.setAttribute('aria-label', 'Delete ' + text);
  del.addEventListener('click', () => {{
    if (BUG_DELETE) return;
    li.remove();
    if (!BUG_COUNTER) {{ n--; count.textContent = n; }}
  }});
  li.append(span, ' ', del);
  document.getElementById('todo-list').append(li);
  n++; count.textContent = n; input.value = '';
}});
</script></body></html>"""
