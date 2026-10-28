# Tiny demo — Security Analyzer Agent

Two files, two findings, two different outcomes. Upload this folder (or `tiny_demo.zip`) in the console.

Run the tests:
```
python -m unittest discover -s tests
```

## What the agent will do

| # | File | Issue | Expected outcome |
|---|------|-------|-----------------|
| 1 | `src/search.py` (called via `api.handle_search`) | **SQL injection** — f-string interpolation of `name` into a SQL query | ✅ **Fix applied, tests pass → awaiting your approval** |
| 2 | `src/ping.py` (called via `api.handle_ping`) | **Command injection** — `subprocess.run` with `shell=True` and user-supplied `host` | 🔄 **Needs a person** — removing `shell=True` changes the command's behaviour |

After the run:
- **Approve** finding #1 and the patch is ready to apply
- Finding #2 stays with you to redesign safely
