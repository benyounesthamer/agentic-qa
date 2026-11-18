# Benchmark results

Model: `openai/gpt-oss-120b` on Groq · 2026-11-18 · one run per scenario

**5 of 6 completed scenarios correct.** The 7th (`heal/redesign+counter`) did not complete: the provider's daily token quota ran out during it.

A scenario is correct when no test is left failing, the planted bug (if any) is the one reported, nothing else is reported as a bug, and no test was deleted along the way.

| Scenario | Expected | Passed | Failed | Bugs reported | False reports | Repairs | Correct |
|---|---|---|---|---|---|---|---|
| write/clean | all green, no bug reported | 5 | 0 | 0 | 0 | 1 | yes |
| write/counter | report the counter bug | 4 | 0 | 1 | 0 | 2 | yes |
| write/empty | report the empty bug | 4 | 1 | 0 | 0 | 3 | NO |
| write/login | report the login bug | 4 | 0 | 1 | 0 | 1 | yes |
| write/delete | report the delete bug | 4 | 0 | 2 | 0 | 2 | yes |
| heal/redesign | all green, no bug reported | 5 | 0 | 0 | 0 | 2 | yes |
| heal/redesign+counter | report the counter bug | — | — | — | — | — | not completed |

In `write/delete` both bug reports describe the planted defect ("task remains visible after deletion"), so neither is a false report.

## Earlier runs

| Run | Scoring | Result | What changed afterwards |
|---|---|---|---|
| 1 | lenient | 5 / 7 | Fixed attribute names in page descriptions; Playwright rules in the prompt; repair sees its earlier diagnoses |
| 2 | lenient | 4 / 7 | Stopped by the per-minute rate limit. Revealed a repair that deleted passing tests and one false bug report: added the deleted-tests guard and the stricter scoring |
| 3 | strict | 3 / 5 | Clean scenario lost to a network error; heal scenarios skipped as a result |
| 4 | strict | 5 / 6 | This table |

The tables from runs 1 to 3 are kept in [history/](history/).

Results vary between runs: the counter bug was missed in runs 1 and 3 and caught in run 4, while the empty-task bug was caught in runs 1 and 3 and missed in run 4. Several runs per scenario are needed before quoting a rate.
