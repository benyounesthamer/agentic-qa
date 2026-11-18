# Benchmark results

Model: `openai/gpt-oss-120b` · 2026-11-17 · one run per scenario

**3 of 5 scenarios correct.**

A scenario is correct when no test is left failing, the planted bug (if any) is the one reported,
nothing else is reported as a bug, and no test was deleted along the way.

| Scenario | Expected | Passed | Failed | Bugs reported | False reports | Repairs | LLM calls | Time | Correct |
|---|---|---|---|---|---|---|---|---|---|
| write/clean |  | 0 | 0 | 0 | 0 | 0 | 1 | 1281s | NO |
| write/counter | report the counter bug | 4 | 1 | 0 | 0 | 3 | 8 | 9143s | NO |
| write/empty | report the empty bug | 4 | 0 | 1 | 0 | 1 | 6 | 2394s | yes |
| write/login | report the login bug | 4 | 0 | 1 | 0 | 1 | 6 | 29201s | yes |
| write/delete | report the delete bug | 4 | 0 | 1 | 0 | 3 | 8 | 124s | yes |
