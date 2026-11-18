# Benchmark results

Model: `openai/gpt-oss-120b` · 2026-11-17 · one run per scenario

**5 of 7 scenarios correct.**

| Scenario | Expected | Passed | Failed | Bugs reported | Repairs | LLM calls | Time | Correct |
|---|---|---|---|---|---|---|---|---|
| write/clean | all green, no bug reported | 5 | 0 | 0 | 1 | 6 | 58s | yes |
| write/counter | bug reported | 1 | 4 | 0 | 3 | 8 | 196s | NO |
| write/empty | bug reported | 5 | 0 | 1 | 1 | 6 | 95s | yes |
| write/login | bug reported | 4 | 0 | 1 | 1 | 6 | 96s | yes |
| write/delete | bug reported | 4 | 1 | 0 | 3 | 8 | 172s | NO |
| heal/redesign | all green, no bug reported | 5 | 0 | 0 | 1 | 4 | 69s | yes |
| heal/redesign+counter | bug reported | 4 | 0 | 1 | 2 | 5 | 101s | yes |
