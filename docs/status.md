# Security Analyzer Agent: status summary

Everything below describes work already committed and pushed to `master`
(https://github.com/anshusharma-ipl/Security_Analyzer_Agent_IPL), remote head `06006c7`.
`canvas.md` is the source of truth and `golden/` is never edited.

## Steps done

### 1. Project setup (`df25847`)
- The project folder is its own git repo on `master`, with remote `origin` on GitHub.
- Added `AGENTS.md` (team decisions), `README.md` and `.gitignore` (ignores `.env`, `out/`, `tmp/`, `traces/`).

### 2. Contracts: JSON schemas (`d15c11f`)
- Schemas for the input, the rules file, the final output and the shared `state`.
- One schema for each of the seven tools.
- `validate.py` checks 69 sample payloads against these schemas.

### 3. The seven tools (`37c8734`)
- Read-only: `list_files`, `read_file`, `read_code_structure`, `run_security_rules`.
- Write-capable: `apply_patch`, `run_tests`, `request_recheck`. They accept only the temporary copy.
- Orchestrator helpers (not tools, never exposed to agents): `make_temp_copy`, `hash_originals`, `verify_originals`.
- Safety: `_safety.py` and `_workspace.py` block paths that escape the folder; `_mask.py` hides secrets.

### 4. MCP server (`42c1224`)
`python tools/mcp_server.py --agent <name>` gives each agent only its allowed tools:

| Agent | Tools |
| --- | --- |
| auditor | `list_files`, `read_file`, `run_security_rules` |
| investigator | `read_file`, `read_code_structure` |
| fixer-validator | `apply_patch`, `run_tests`, `request_recheck` |

30 tests cover it, including that an agent is refused a tool it does not own.

### 5. Golden table and a rule fix (`0419f68`)
- `evals/golden_table.py` runs the tools alone on the 11 golden cases. All 11 match `expected.json`.
- It exposed a real bug: the PATH rule flagged `os.path.join(folder, "a.txt")`.
  The tool was fixed (not `expected.json`) and a regression test was added.

### 6. Roster document (`73c00d8`)
- `docs/roster.md`: single vs multi-agent, three-sentence test per role, Auditor options (a) and (b)
  with a recommendation for (b) (the owner then chose (a)) and a Mermaid diagram.
- Added `handoff_log` to the state schema; its length must equal the step count.

### 7. Agents (`fe66163`)
- Prompt files `agents/auditor.md`, `investigator.md`, `fixer_validator.md`. Each states the agent's single
  decision, its only tools, its exact output fields, and the rule that code is untrusted data.
- `agents/mcp_client.py` starts the MCP server for an agent.
- `agents/offline_agents.py`: deterministic stand-ins for the three agents, because no model endpoint exists.
- `read_file` now masks secrets as `<SECRET_n>`, `<EMAIL_n>`, `<PHONE_n>`.

### 8. Orchestrator (`fe66163`, then `06006c7`)
Plain code, not an agent. Fixed steps:
1. Validate `rules.json`.
2. Fingerprint the originals and make the temporary copy.
3. Run the Auditor.
4. For each ranked finding, run the Investigator, then the Fixer & Validator.
   Decision order: limits, evidence, tests, unclear cause, `fix_allowed`, fix with one retry.
5. Write `review_queue.json` and wait for a person to approve, edit or reject.
6. Run `verify_originals`. If an original changed, the run stops with an alert.
7. Write the decision log, `report.json`, `report.md` and `fixes.patch`.

- State is validated before each handoff; an agent's output is accepted only if it writes just the fields it owns.
- `state.json` is saved after every handoff, with numbered copies in `states/`.
- The fix is never applied to the original folder.
- `orchestrator/cli.py` commands: `run <source> <rules> [--out DIR] [--policy JSON]` and `finish <run_dir>`.

### 9. Clean-up and push (`06006c7`)
- Patches now list removed lines first; snapshot names no longer double the step number.
- All checks run, committed and pushed. Working tree clean.

## Tests run

| Check | Result |
| --- | --- |
| `python -m unittest discover -s tests` | 74 pass (43 tools, 30 MCP, plus the import rule) |
| `python validate.py` | 69 of 69 |
| `python golden/verify_golden.py` | all cases as expected |
| `python tools/mcp_server.py --check` | passed |
| `python evals/golden_table.py` | 11 of 11 |
| Case_01 end-to-end | reached `waiting_for_review` (scratch folder `tmp/out_try`) |

**Not tested yet:** `tests/test_agents.py` and `tests/test_orchestrator.py` do not exist. Caps, retries,
tamper detection, edited patches and the `verify_originals` stop rule are untested.

## Findings

### Case_01 (`golden/case_01_sqli_fstring`)
- One SQL injection: `F001`, rule `SQLI`, severity high, `src/users.py:2`.
- Evidence: `query = f"SELECT id, name FROM users WHERE name = '{name}'"`.
- Tests passed before and after; the re-check was clear; status `verified_awaiting_approval`.
- Proposed fix: a parameterized query, `conn.execute(query, (name,))`.
- Nothing is approved or applied; `golden/case_01` is untouched.
- The traced cause is weak: it only says no caller of `find_user` was found.

### Bugs found and fixed
- PATH rule false positive on `os.path.join(folder, "a.txt")`.
- `read_file` did not mask secrets.
- Patch lines were interleaved instead of removals first.
- Snapshot file names had a doubled step number.

### Limits of the offline stand-ins
- Case_11 (no callers, should escalate) looks like case_01 in code, so it would get a fix. Needs a model or a decision.
- The Fixer only writes a patch for `query = f"... '{value}' ..."` followed by `.execute(query)` (cases 01, 09, 10).
- The Investigator hands case_07 to a person.

## Next steps
1. Write `tests/test_agents.py` and `tests/test_orchestrator.py`.
2. Run case_01 into `out/`, then approve, edit or reject in `review_queue.json` and run `finish`
   to get `fixes.patch` and the report.
3. Record the confirmed decisions in `docs/roster.md` and `AGENTS.md`.
