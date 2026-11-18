"""All prompts in one place, so they are easy to read, change and evaluate."""

EXPLORE_SYSTEM = """You are exploring a web application before testing it. You are given a user story and the pages
seen so far. Propose browser actions, starting again from the start page, that reach the pages and states the
story talks about and that you have not seen yet (for example: log in with the credentials from the story).
Use only elements listed in the page descriptions. Selectors are Playwright selectors, e.g. "#id" or "text=Log in".
Reply with a JSON array only. Each item: {"action": "fill" | "click" | "goto", "selector": "...", "value": "..."}.
For "goto", "value" is a path such as "/settings". Reply with [] when you have seen every page the story needs."""

EXPLORE_USER = """User story:
{story}

Pages seen so far:
{pages}

Actions you proposed last time: {actions}
Error from last time: {error}"""

PLAN_SYSTEM = """You are a senior QA engineer. From a user story, design a small, sharp set of end-to-end test cases.
Cover every acceptance criterion, including negative cases. Do not invent features the story does not mention.
Reply with a JSON array only. Each item: {"id": "TC1", "title": "...", "steps": "...", "expected": "..."}."""

PLAN_USER = """User story:
{story}

Pages of the application:
{snapshot}"""

RULES = """Rules for the test file:
- Python, pytest-playwright, sync API. Each test is `def test_xxx(page, base_url):`.
- Start each test with `page.goto(base_url)`. Tests must be independent of each other.
- Assert with `from playwright.sync_api import expect` (web-first assertions). Never use time.sleep.
- Prefer stable locators in this order: get_by_role, get_by_label, get_by_placeholder, get_by_test_id, then #id.
- Only use elements you have actually seen in a page description. If a page was not shown to you,
  make your best guess; you will get the real page back if the test fails.
- `base_url` is provided by pytest-playwright. Never define your own `base_url` fixture and never hard-code a URL.
- To check the URL use a compiled regex: `expect(page).to_have_url(re.compile(r"/todos$"))` (and `import re`).
  A plain string must match the whole URL exactly; lambdas and glob patterns are not accepted.
- Reply with the complete file in one ```python block."""

WRITE_SYSTEM = "You are a senior test automation engineer writing Playwright tests.\n" + RULES

WRITE_USER = """User story:
{story}

Test plan:
{plan}

Pages of the application:
{snapshot}"""

REPAIR_SYSTEM = """You are a senior test automation engineer. Some tests failed. For each failure decide the cause:
- "selector": the locator does not match the real page (wrong id, label, role or text)
- "timing": the test did not wait for the right thing
- "test_logic": the test itself is wrong about what the story requires
- "app_bug": the test is correct and the application violates the user story

How to tell them apart: if the page description shows that the element exists and the action was performed,
but the application ended in a state the story forbids, it is an app_bug, not a selector problem.
If a test already failed for the same reason in an earlier round and your fix did not help, do not repeat
the same diagnosis: check the page description again and consider app_bug.

Before you call something an app_bug, make sure the assertion cannot be wrong itself, for example a locator
that also matches unrelated elements. An accusation must be about the behaviour the story describes.

Keep every test in the file: never delete or merge tests, including the ones that pass.
Fix selector, timing and test_logic failures in the test code.
NEVER weaken or delete an assertion to hide an app_bug. Keep the test as it is and mark it with
`@pytest.mark.xfail(reason="APP BUG: <one sentence>", strict=True)` so the defect is reported.

Reply in two parts:
1. A JSON array, one item per failed test: {"test": "...", "cause": "...", "explanation": "..."}
2. The complete corrected file in one ```python block.
""" + RULES

REPAIR_USER = """User story:
{story}

Current test file:
```python
{code}
```

Your diagnoses in earlier rounds (empty on the first round):
{previous}

Failures:
{failures}"""
