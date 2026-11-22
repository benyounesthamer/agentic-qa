"""NovaBank: a small but realistic online-banking app used as the system under test.

Each browser session gets its own fresh data, so tests never affect each other.

Switches (environment variables):
  DEMO_UI_VERSION=2   a redesign: element ids and labels change, so existing tests break
  DEMO_BUG=<names>    plant one or more defects (comma-separated), see BUGS below
"""
from __future__ import annotations

import os
import secrets
from datetime import date
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from html import escape

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

BUGS = {
    "limit": "the daily transfer limit is not enforced",
    "negative": "a negative transfer amount is accepted (and credits the account)",
    "overdraft": "a transfer larger than the balance is accepted",
    "balance": "the balance is not debited after a transfer",
    "rounding": "the debited amount is truncated to whole dinars",
    "iban": "an IBAN with a wrong checksum is accepted",
    "delete": "deleting a beneficiary does nothing",
    "statement": "completed transfers are missing from the statement",
    "logout": "logging out does not end the session",
}
DAILY_LIMIT = Decimal("5000")
USER, PASSWORD = "demo", "demo123"

app = FastAPI(title="NovaBank demo")
SESSIONS: dict[str, dict] = {}


def bugs() -> set[str]:
    return {b.strip() for b in os.getenv("DEMO_BUG", "").split(",") if b.strip()}


def v2() -> bool:
    return os.getenv("DEMO_UI_VERSION", "1") == "2"


# Labels and ids that change in the redesign (v1, v2)
L = {
    "nav_accounts": ("Accounts", "My accounts"), "nav_transfer": ("Transfer", "Payments"),
    "nav_benef": ("Beneficiaries", "Payees"), "nav_statements": ("Statements", "History"),
    "login_btn": ("Log in", "Sign in"), "continue": ("Continue", "Review transfer"),
    "confirm": ("Confirm transfer", "Send money"), "add_benef": ("Add beneficiary", "Save payee"),
    "logout": ("Log out", "Sign out"),
    "id_user": ("username", "login-id"), "id_pass": ("password", "login-secret"),
    "id_from": ("from-account", "source"), "id_benef": ("beneficiary", "payee"),
    "id_amount": ("amount", "transfer-amount"), "id_ref": ("reference", "memo"),
    "id_bname": ("benef-name", "payee-name"), "id_biban": ("benef-iban", "payee-iban"),
}


def t(key: str) -> str:
    return L[key][1 if v2() else 0]


# ---------- money and IBAN ----------

def fmt(amount: Decimal) -> str:
    """Tunisian dinars have 3 decimals (millimes): 3,250.750 TND."""
    return f"{amount:,.3f} TND"


def iban_checksum_ok(iban: str) -> bool:
    s = iban[4:] + iban[:4]
    digits = "".join(str(int(c, 36)) for c in s)
    return int(digits) % 97 == 1


def make_iban(bban: str) -> str:
    """Build a valid Tunisian IBAN (TN + 2 check digits + 20 digits) from a 20-digit BBAN."""
    check = 98 - int("".join(str(int(c, 36)) for c in bban + "TN00")) % 97
    return f"TN{check:02d}{bban}"


def pretty_iban(iban: str) -> str:
    return " ".join(iban[i:i + 4] for i in range(0, len(iban), 4))


def validate_iban(raw: str) -> tuple[str | None, str]:
    iban = raw.replace(" ", "").upper()
    if not (len(iban) == 24 and iban.startswith("TN") and iban[2:].isdigit()):
        return None, "A Tunisian IBAN has 24 characters: TN followed by 22 digits."
    if "iban" not in bugs() and not iban_checksum_ok(iban):
        return None, "This IBAN is not valid (wrong check digits)."
    return iban, ""


# ---------- session state ----------

def new_state() -> dict:
    today = date.today().isoformat()
    return {
        "user": None,
        "accounts": {
            "CUR": {"name": "Current account", "iban": make_iban("04001234567890123456"), "balance": Decimal("3250.750")},
            "SAV": {"name": "Savings account", "iban": make_iban("04001234567890987654"), "balance": Decimal("8400.000")},
        },
        "beneficiaries": [
            {"id": 1, "name": "Sami Ben Ali", "iban": make_iban("08005000123456789012")},
            {"id": 2, "name": "Leila Trabelsi", "iban": make_iban("10002000987654321098")},
        ],
        "transactions": [
            {"date": today, "account": "CUR", "label": "Salary", "amount": Decimal("2800.000")},
            {"date": today, "account": "CUR", "label": "Card payment - supermarket", "amount": Decimal("-86.400")},
        ],
        "sent_today": Decimal("0"),
        "pending": None,
        "next_id": 3,
    }


def session(request: Request) -> tuple[str, dict]:
    sid = request.cookies.get("sid")
    if not sid or sid not in SESSIONS:
        sid = secrets.token_hex(8)
        SESSIONS[sid] = new_state()
    return sid, SESSIONS[sid]


def respond(sid: str, body: str | RedirectResponse) -> HTMLResponse | RedirectResponse:
    resp = body if isinstance(body, RedirectResponse) else HTMLResponse(body)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    # banking pages must not be cached: otherwise the browser's Back button shows balances after logout
    # (found by the QA agent itself in an early run, before this header was added)
    resp.headers["Cache-Control"] = "no-store"
    return resp


def go(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


# ---------- layout ----------

CSS = """
:root{--bg:#f4f6f8;--card:#fff;--text:#16202a;--muted:#5d6b78;--line:#dde3e9;--brand:#0b5a7a;--brand2:#0e7aa6;
--ok:#1d7a46;--err:#b3261e;--errbg:#fdecea;--okbg:#e8f5ee}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
header{background:var(--brand);color:#fff}header .in{max-width:980px;margin:0 auto;padding:14px 20px;display:flex;align-items:center;gap:28px}
.logo{font-weight:700;font-size:19px;letter-spacing:.3px}.logo span{opacity:.7;font-weight:400;font-size:13px;margin-left:6px}
nav{display:flex;gap:4px;flex:1}nav a{color:#dcecf3;text-decoration:none;padding:6px 12px;border-radius:6px}
nav a.on,nav a:hover{background:rgba(255,255,255,.14);color:#fff}
header form button{background:transparent;border:1px solid rgba(255,255,255,.5);color:#fff;padding:5px 12px;border-radius:6px;cursor:pointer}
main{max-width:980px;margin:28px auto;padding:0 20px}h1{font-size:24px;margin:0 0 18px}h2{font-size:17px;margin:28px 0 10px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px}
.card .k{color:var(--muted);font-size:13px}.card .bal{font-size:26px;font-weight:650;margin:6px 0 2px}
.iban{font-family:ui-monospace,Consolas,monospace;font-size:13px;color:var(--muted)}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
th,td{text-align:left;padding:10px 14px;border-bottom:1px solid var(--line)}th{font-size:12px;text-transform:uppercase;color:var(--muted);letter-spacing:.04em}
td.num{text-align:right;font-variant-numeric:tabular-nums}.neg{color:var(--err)}.pos{color:var(--ok)}
form.box{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:22px;max-width:520px}
label{display:block;font-weight:550;margin:14px 0 6px}label:first-child{margin-top:0}
input,select{width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:8px;font:inherit;background:#fff}
.btn{margin-top:18px;background:var(--brand2);color:#fff;border:0;border-radius:8px;padding:10px 18px;font:inherit;font-weight:600;cursor:pointer}
.btn.small{margin:0;padding:5px 12px;font-size:13px;background:#fff;color:var(--err);border:1px solid var(--line)}
.alert{padding:12px 14px;border-radius:8px;margin-bottom:16px}.alert.err{background:var(--errbg);color:var(--err)}.alert.ok{background:var(--okbg);color:var(--ok)}
.summary td:first-child{color:var(--muted);width:40%}.hint{color:var(--muted);font-size:13px;margin-top:6px}
.center{max-width:400px;margin:70px auto}
"""


def page(title: str, body: str, state: dict | None = None, active: str = "") -> str:
    nav = ""
    if state and state.get("user"):
        links = [("accounts", "/accounts", t("nav_accounts")), ("transfer", "/transfer", t("nav_transfer")),
                 ("benef", "/beneficiaries", t("nav_benef")), ("statements", "/statements", t("nav_statements"))]
        items = "".join(f'<a href="{u}" class="{"on" if k == active else ""}">{n}</a>' for k, u, n in links)
        nav = (f'<nav>{items}</nav><form method="post" action="/logout">'
               f'<button type="submit">{t("logout")}</button></form>')
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{escape(title)} - NovaBank</title>'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><style>{CSS}</style></head><body>'
            f'<header><div class="in"><div class="logo">NovaBank<span>demo</span></div>{nav}</div></header>'
            f'<main>{body}</main></body></html>')


def alert(msg: str, kind: str = "err") -> str:
    return f'<div class="alert {kind}" role="{"alert" if kind == "err" else "status"}">{escape(msg)}</div>' if msg else ""


def need_login(state: dict) -> bool:
    return not state.get("user")


# ---------- login ----------

@app.get("/")
def home(request: Request):
    sid, state = session(request)
    return respond(sid, go("/accounts" if state["user"] else "/login"))


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: str = ""):
    sid, state = session(request)
    body = (f'<div class="center"><h1>Welcome to NovaBank</h1>{alert(error)}<form class="box" method="post" action="/login">'
            f'<label for="{t("id_user")}">Username</label><input id="{t("id_user")}" name="username" autocomplete="off">'
            f'<label for="{t("id_pass")}">Password</label><input id="{t("id_pass")}" name="password" type="password">'
            f'<button class="btn" type="submit">{t("login_btn")}</button></form></div>')
    return respond(sid, page("Log in", body))


@app.post("/login")
def login(request: Request, username: str = Form(""), password: str = Form("")):
    sid, state = session(request)
    if username == USER and password == PASSWORD:
        SESSIONS[sid] = new_state()  # fresh data on every login
        SESSIONS[sid]["user"] = username
        return respond(sid, go("/accounts"))
    return respond(sid, go("/login?error=Invalid+username+or+password."))


@app.post("/logout")
def logout(request: Request):
    sid, state = session(request)
    if "logout" not in bugs():
        state["user"] = None
    return respond(sid, go("/login"))


# ---------- accounts ----------

def tx_rows(txs: list[dict]) -> str:
    rows = "".join(
        f'<tr><td>{tx["date"]}</td><td>{escape(tx["label"])}</td>'
        f'<td class="num {"neg" if tx["amount"] < 0 else "pos"}">{fmt(tx["amount"])}</td></tr>' for tx in reversed(txs))
    return rows or '<tr><td colspan="3">No transactions.</td></tr>'


@app.get("/accounts", response_class=HTMLResponse)
def accounts(request: Request):
    sid, state = session(request)
    if need_login(state):
        return respond(sid, go("/login"))
    cards = "".join(
        f'<div class="card" data-testid="account-{k}"><div class="k">{a["name"]}</div>'
        f'<div class="bal" data-testid="balance-{k}">{fmt(a["balance"])}</div>'
        f'<div class="iban">{pretty_iban(a["iban"])}</div></div>' for k, a in state["accounts"].items())
    visible = [tx for tx in state["transactions"] if not tx.get("hidden")]
    body = (f'<h1>{t("nav_accounts")}</h1><div class="cards">{cards}</div><h2>Recent transactions</h2>'
            f'<table><tr><th>Date</th><th>Description</th><th style="text-align:right">Amount</th></tr>{tx_rows(visible[-5:])}</table>')
    return respond(sid, page("Accounts", body, state, "accounts"))


# ---------- transfers ----------

def transfer_form(state: dict, error: str = "", values: dict | None = None) -> str:
    v = values or {}
    acc = "".join(f'<option value="{k}" {"selected" if v.get("from") == k else ""}>{a["name"]} - {fmt(a["balance"])}</option>'
                  for k, a in state["accounts"].items())
    ben = '<option value="">Choose a beneficiary</option>' + "".join(
        f'<option value="{b["id"]}" {"selected" if str(v.get("to")) == str(b["id"]) else ""}>{escape(b["name"])}</option>'
        for b in state["beneficiaries"])
    left = DAILY_LIMIT - state["sent_today"]
    return (f'<h1>New transfer</h1>{alert(error)}<form class="box" method="post" action="/transfer">'
            f'<label for="{t("id_from")}">From account</label><select id="{t("id_from")}" name="from_account">{acc}</select>'
            f'<label for="{t("id_benef")}">Beneficiary</label><select id="{t("id_benef")}" name="beneficiary">{ben}</select>'
            f'<label for="{t("id_amount")}">Amount (TND)</label>'
            f'<input id="{t("id_amount")}" name="amount" inputmode="decimal" value="{escape(v.get("amount", ""))}">'
            f'<div class="hint">Daily limit {fmt(DAILY_LIMIT)} · {fmt(left)} left today</div>'
            f'<label for="{t("id_ref")}">Reference</label><input id="{t("id_ref")}" name="reference" value="{escape(v.get("ref", ""))}">'
            f'<button class="btn" type="submit">{t("continue")}</button></form>')


@app.get("/transfer", response_class=HTMLResponse)
def transfer_page(request: Request):
    sid, state = session(request)
    if need_login(state):
        return respond(sid, go("/login"))
    return respond(sid, page("Transfer", transfer_form(state), state, "transfer"))


def check_transfer(state: dict, src: str, to: str, raw_amount: str) -> tuple[Decimal | None, str]:
    b = bugs()
    if src not in state["accounts"]:
        return None, "Choose the account to debit."
    if not any(str(x["id"]) == to for x in state["beneficiaries"]):
        return None, "Choose a beneficiary."
    try:
        amount = Decimal(raw_amount.replace(",", ".").replace(" ", ""))
    except InvalidOperation:
        return None, "Enter a valid amount."
    if amount.as_tuple().exponent < -3:
        return None, "Amounts have at most 3 decimals (millimes)."
    if amount <= 0 and "negative" not in b:
        return None, "The amount must be greater than zero."
    if amount > state["accounts"][src]["balance"] and "overdraft" not in b:
        return None, "Insufficient balance on this account."
    if state["sent_today"] + amount > DAILY_LIMIT and "limit" not in b:
        return None, f"This transfer exceeds your daily limit of {fmt(DAILY_LIMIT)}."
    return amount, ""


@app.post("/transfer", response_class=HTMLResponse)
def transfer_submit(request: Request, from_account: str = Form(""), beneficiary: str = Form(""),
                    amount: str = Form(""), reference: str = Form("")):
    sid, state = session(request)
    if need_login(state):
        return respond(sid, go("/login"))
    value, error = check_transfer(state, from_account, beneficiary, amount)
    if error:
        values = {"from": from_account, "to": beneficiary, "amount": amount, "ref": reference}
        return respond(sid, page("Transfer", transfer_form(state, error, values), state, "transfer"))
    ben = next(x for x in state["beneficiaries"] if str(x["id"]) == beneficiary)
    state["pending"] = {"from": from_account, "to": ben, "amount": value, "ref": reference.strip() or "Transfer"}
    acc = state["accounts"][from_account]
    body = (f'<h1>Confirm your transfer</h1><table class="summary">'
            f'<tr><td>From</td><td>{acc["name"]}</td></tr><tr><td>To</td><td>{escape(ben["name"])}<br>'
            f'<span class="iban">{pretty_iban(ben["iban"])}</span></td></tr>'
            f'<tr><td>Amount</td><td data-testid="confirm-amount">{fmt(value)}</td></tr>'
            f'<tr><td>Reference</td><td>{escape(state["pending"]["ref"])}</td></tr></table>'
            f'<form method="post" action="/transfer/confirm"><button class="btn" type="submit">{t("confirm")}</button></form>')
    return respond(sid, page("Confirm", body, state, "transfer"))


@app.post("/transfer/confirm", response_class=HTMLResponse)
def transfer_confirm(request: Request):
    sid, state = session(request)
    if need_login(state):
        return respond(sid, go("/login"))
    p = state.pop("pending", None)
    state["pending"] = None
    if not p:
        return respond(sid, go("/transfer"))
    b = bugs()
    debit = p["amount"].quantize(Decimal("1"), rounding=ROUND_DOWN) if "rounding" in b else p["amount"]
    acc = state["accounts"][p["from"]]
    if "balance" not in b:
        acc["balance"] -= debit
    state["sent_today"] += p["amount"]
    state["transactions"].append({"date": date.today().isoformat(), "account": p["from"],
                                  "label": f'Transfer to {p["to"]["name"]} - {p["ref"]}', "amount": -debit,
                                  "hidden": "statement" in b})
    body = (f'{alert("Transfer completed.", "ok")}<h1>Transfer sent</h1><table class="summary">'
            f'<tr><td>Amount</td><td>{fmt(p["amount"])}</td></tr><tr><td>To</td><td>{escape(p["to"]["name"])}</td></tr>'
            f'<tr><td>New balance</td><td data-testid="new-balance">{fmt(acc["balance"])}</td></tr></table>')
    return respond(sid, page("Transfer sent", body, state, "transfer"))


# ---------- beneficiaries ----------

def benef_page(state: dict, error: str = "", ok: str = "") -> str:
    rows = "".join(
        f'<tr><td>{escape(b["name"])}</td><td class="iban">{pretty_iban(b["iban"])}</td><td>'
        f'<form method="post" action="/beneficiaries/{b["id"]}/delete">'
        f'<button class="btn small" aria-label="Delete {escape(b["name"])}">Delete</button></form></td></tr>'
        for b in state["beneficiaries"]) or '<tr><td colspan="3">No beneficiaries.</td></tr>'
    return (f'<h1>{t("nav_benef")}</h1>{alert(error)}{alert(ok, "ok")}'
            f'<table><tr><th>Name</th><th>IBAN</th><th></th></tr>{rows}</table>'
            f'<h2>{t("add_benef")}</h2><form class="box" method="post" action="/beneficiaries">'
            f'<label for="{t("id_bname")}">Name</label><input id="{t("id_bname")}" name="name">'
            f'<label for="{t("id_biban")}">IBAN</label><input id="{t("id_biban")}" name="iban" placeholder="TN59 ...">'
            f'<button class="btn" type="submit">{t("add_benef")}</button></form>')


@app.get("/beneficiaries", response_class=HTMLResponse)
def beneficiaries(request: Request):
    sid, state = session(request)
    if need_login(state):
        return respond(sid, go("/login"))
    return respond(sid, page("Beneficiaries", benef_page(state), state, "benef"))


@app.post("/beneficiaries", response_class=HTMLResponse)
def add_beneficiary(request: Request, name: str = Form(""), iban: str = Form("")):
    sid, state = session(request)
    if need_login(state):
        return respond(sid, go("/login"))
    if not name.strip():
        return respond(sid, page("Beneficiaries", benef_page(state, "Enter the beneficiary's name."), state, "benef"))
    clean, error = validate_iban(iban)
    if error:
        return respond(sid, page("Beneficiaries", benef_page(state, error), state, "benef"))
    state["beneficiaries"].append({"id": state["next_id"], "name": name.strip(), "iban": clean})
    state["next_id"] += 1
    return respond(sid, page("Beneficiaries", benef_page(state, ok="Beneficiary added."), state, "benef"))


@app.post("/beneficiaries/{bid}/delete")
def delete_beneficiary(request: Request, bid: int):
    sid, state = session(request)
    if need_login(state):
        return respond(sid, go("/login"))
    if "delete" not in bugs():
        state["beneficiaries"] = [b for b in state["beneficiaries"] if b["id"] != bid]
    return respond(sid, go("/beneficiaries"))


# ---------- statements ----------

@app.get("/statements", response_class=HTMLResponse)
def statements(request: Request, account: str = "CUR"):
    sid, state = session(request)
    if need_login(state):
        return respond(sid, go("/login"))
    account = account if account in state["accounts"] else "CUR"
    opts = "".join(f'<option value="{k}" {"selected" if k == account else ""}>{a["name"]}</option>'
                   for k, a in state["accounts"].items())
    txs = [tx for tx in state["transactions"] if tx["account"] == account and not tx.get("hidden")]
    body = (f'<h1>{t("nav_statements")}</h1><form method="get" action="/statements" style="max-width:320px;margin-bottom:16px">'
            f'<label for="statement-account">Account</label>'
            f'<select id="statement-account" name="account" onchange="this.form.submit()">{opts}</select></form>'
            f'<table><tr><th>Date</th><th>Description</th><th style="text-align:right">Amount</th></tr>{tx_rows(txs)}</table>')
    return respond(sid, page("Statements", body, state, "statements"))
