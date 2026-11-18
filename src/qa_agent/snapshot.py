"""Turn live pages into short lists of visible elements the LLM can write selectors for."""
from __future__ import annotations

SNAPSHOT_JS = """() => Array.from(document.querySelectorAll(
    'a,button,input,select,textarea,label,h1,h2,h3,li,p,span,[role],[data-testid]'))
  .filter(e => e.offsetParent !== null)
  .map(e => ({
    tag: e.tagName.toLowerCase(), id: e.id || null, name: e.getAttribute('name'),
    type: e.getAttribute('type'), role: e.getAttribute('role'),
    testid: e.getAttribute('data-testid'), placeholder: e.getAttribute('placeholder'),
    aria_label: e.getAttribute('aria-label'),
    text: (e.children.length ? '' : (e.innerText || '')).trim().slice(0, 80)
  }))
  .filter(e => ['input','select','textarea','button','a'].includes(e.tag) || e.text || e.role)
  .slice(0, 80)"""


NAMES = {"aria_label": "aria-label", "testid": "data-testid"}


def format_snapshot(url: str, elements: list[dict]) -> str:
    lines = [f"URL: {url}"]
    for e in elements:
        # print the real HTML attribute names, so the model can copy them into selectors
        attrs = " ".join(f'{NAMES.get(k, k)}="{v}"' for k, v in e.items() if v and k not in ("tag", "text"))
        lines.append(f"  <{e['tag']} {attrs}>{e.get('text') or ''}".rstrip())
    return "\n".join(lines)


def explore(base_url: str, actions: list[dict] | None = None) -> tuple[dict[str, str], str]:
    """Open the app, perform `actions`, and describe every distinct page seen on the way.

    Each action is {"action": "goto" | "fill" | "click", "selector": "...", "value": "..."}.
    Returns ({url: description}, error). `error` is empty unless an action could not be done;
    it is given back to the model so it can correct its next attempt.
    """
    from playwright.sync_api import sync_playwright

    pages: dict[str, str] = {}
    error = ""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_default_timeout(4000)

        def record() -> None:
            # a click can trigger a request and then a redirect: let both settle before looking
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(400)
            page.wait_for_load_state("networkidle")
            pages[page.url] = format_snapshot(page.url, page.evaluate(SNAPSHOT_JS))

        page.goto(base_url)
        record()
        for a in actions or []:
            try:
                kind = a.get("action")
                if kind == "goto":
                    page.goto(base_url.rstrip("/") + "/" + str(a.get("value", "")).lstrip("/"))
                elif kind == "fill":
                    page.locator(a["selector"]).fill(str(a.get("value", "")))
                elif kind == "click":
                    page.locator(a["selector"]).click()
                else:
                    raise ValueError(f"unknown action {kind!r}")
                record()  # same URL: the description is refreshed with what the page shows now
            except Exception as exc:
                error = f"Action {a} failed: {str(exc).splitlines()[0]}"
                break
        browser.close()
    return pages, error
