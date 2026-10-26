# Golden dataset: Security Analyzer Agent

11 tiny Python projects, one for each of the 11 case types in the canvas. Each folder has:

- `src/`: the code to scan
- `tests/`: its tests (missing on purpose in one case)
- `expected.json`: the right answer (status, where the finding is, the fix in one line, why)

`golden_index.csv` lists every case in plain words (input, expected output, why it is in the set).
`rules.json` is a sample rules file for these cases; replace it with the team's real one.
`python3 verify_golden.py` confirms each case's tests behave as `expected.json` says before any fix.

Expected status values: `verified_awaiting_approval` (fix ready, a person approves), `safe_nothing_to_report` (the code is safe, so the agent lists no problem),
`needs_a_person` (agent stops and hands over).
