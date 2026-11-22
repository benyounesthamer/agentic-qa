# Benchmark results

**In progress.** The NovaBank benchmark has 11 scenarios: a clean app (false-alarm check), each of the 9 planted defects, and a redesign (healing). On a free API tier the daily token quota fits about three banking scenarios, so the table fills in over several days. `python benchmark/run_benchmark.py` resumes where it stopped.

So far:

- **Single runs during development** (see the README): with the overdraft defect planted, the agent wrote 11 of 11 planned tests, reported the overdraft, and found a real defect that had not been planted (balances visible through the browser's Back button after logout).
- **One earlier benchmark run is set aside.** It ran before a client fix: `gpt-oss` models could spend their whole reply budget reasoning and return an empty answer, which the agent then treated as "no change". The scenario will be re-run with the fix.
- **A model comparison point:** on the clean app, Gemini 2.5 Flash reported 3 bugs that do not exist, where `gpt-oss-120b` reported none.

Results on the earlier, simpler todo app are kept in [history/](history/).
