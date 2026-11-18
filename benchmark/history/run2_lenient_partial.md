# Benchmark results

Model: `openai/gpt-oss-120b` · 2026-11-17 · one run per scenario

**4 of 7 scenarios correct.**

| Scenario | Expected | Passed | Failed | Bugs reported | Repairs | LLM calls | Time | Correct |
|---|---|---|---|---|---|---|---|---|
| write/clean | all green, no bug reported | 5 | 0 | 0 | 0 | 5 | 47s | yes |
| write/counter | bug reported | 0 | 0 | 3 | 2 | 7 | 132s | yes |
| write/empty | bug reported | 4 | 0 | 1 | 1 | 6 | 93s | yes |
| write/login | bug reported | 5 | 0 | 1 | 1 | 6 | 92s | yes |
| write/delete |  | 0 | 0 | 0 | 0 | 4 | 344s | NO |
| heal/redesign |  | 0 | 0 | 0 | 0 | 2 | 325s | NO |
| heal/redesign+counter |  | 0 | 0 | 0 | 0 | 1 | 315s | NO |
