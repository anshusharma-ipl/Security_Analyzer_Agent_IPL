# AGENTS.md: Security Analyzer Agent

Source of truth: `canvas.md` (read-only). Section numbers refer to it. Sample rules and cases: `golden/`.
Where the canvas said "to be measured", the team's later decisions are recorded here and marked (team decision).

## 1. Goal
"Given a source-code folder, its automated tests and an approved security-rules file, the Security Analyzer agent finds and ranks the places that break the rules, investigates their causes and prepares tested fixes in a safe copy, without modifying the original files and without applying an unapproved change." (canvas section 4)

## 2. Scope
- MVP is Python projects only (team decision: the golden dataset is Python). One project per run.
- Pilot vulnerability classes: SQLI, CMDI, PATH.
- All six rules in `golden/rules.json` are loaded: SQLI, CMDI, PATH, SECRET, WEAKHASH, DEP-PIN.
- SQLI, CMDI, PATH have `fix_allowed: true`.
- SECRET, WEAKHASH, DEP-PIN have `fix_allowed: false`: reported, never fixed.
  Owner decision, 2026-10-27: they stay report-only. The console shows each as a task for the person (rotate the key, raise the pin, use a password hash) instead of proposing a patch.
- AI-based detection rules are NOT in the pilot. The AI helps with judgement and fixes, not detection.

## 3. Roster (canvas section 10)
- **Auditor**: applies all rules to the whole project, decides which findings have enough evidence, ranks them. Stays an agent (owner decision, 2026-10-27; see `docs/roster.md` section 4). Re-run the "collapse" comparison (Auditor as agent versus plain scan) as a recurring eval.
- **Investigator**: works out how untrusted input reaches one weak spot and which fix approach suits it, or hands to a person.
- **Fixer & Validator**: writes the fix, runs tests, requests a re-check, decides keep, retry once, or reject.
- **Workflow orchestrator**: plain code, NOT an agent. Owns order, limits, approvals, decision log, report. Every hand-off goes through it; agents never call each other.
- Orchestrator steps: validate rules file; create temporary copy; ask a person to approve; enforce limits; check originals unchanged; write decision log; write report.

## 4. Tool permissions (canvas section 9)
| Agent | Tools it may use |
| --- | --- |
| Auditor | `list_files`, `read_file`, `run_security_rules` |
| Investigator | `read_file`, `read_code_structure` |
| Fixer & Validator | `apply_patch`, `run_tests`, `request_recheck` |
| Workflow orchestrator | Not an agent. Runs its own steps (section 3); agents cannot choose or skip them |

`apply_patch` and `run_tests` act on the temporary copy only. `request_recheck` asks the Auditor to re-run the rules on changed files.

### NEVER
- Change original files, or write anywhere outside the temporary copy.
- Commit, push, merge, deploy, or open pull requests.
- Apply a fix without a person's approval, or outside the temporary workspace.
- Send code anywhere except the AI model service; contact any unauthorized network endpoint.
- Send secrets or personal data unhidden to the model (zero tolerance).
- Edit the rules file, or generate rules without security-engineer ownership.
- Add or remove software packages, or delete files.
- Perform large architectural redesigns.
- Replace penetration testing, threat modelling, code review, or the security program.
- Evaluate or rank developers.
- Call a fix "verified" unless tests pass and the re-check is clear.
- Stop rule: if an original file is touched or a write lands outside the temporary copy, stop the run at once and alert.

## 5. Decision order and human triggers (canvas sections 10, 12; team decisions)
Per finding, in this order:
1. Check limits (section 6) and model output first. Cap hit: stop, status `not_processed`. Malformed model output: hand to a person.
2. No proof (file, line and code)? Drop the finding.
3. Check tests before any fix. Tests missing or failing: hand to a person.
4. Cause unclear, or needs a big redesign? Hand to a person. This comes before the fix setting, so a `fix_allowed: false` finding with an unclear cause also goes to a person.
   Console setting `fix_when_cause_unclear` (owner decision, 2026-10-27): **on in the console, off in the engine default and in the evals.** When on, a finding whose only objection is "cause unclear" (no caller visible in the project) still gets a local fix (a `?` placeholder, a command list with no shell, a path check) prepared for approval. The tests and the re-check must pass, the proposal says the cause was not traced, and a person still approves every fix. A needed redesign, and every `fix_allowed: false` rule, still go to a person.
5. The rule's `fix_allowed` is false? Report it, do not fix it (status `needs_a_person`).
6. Otherwise prepare a fix in the temporary copy and test it. Tests pass and re-check clear: a person approves. Otherwise retry once; if it fails again, status `rejected`, listed in the report with evidence.

Confidence: a score 0 to 1 on every finding. The 0.70 gate applies only to findings found by the AI alone; below it, hand to a person. A rule match with an unclear cause goes to a person for that reason, not for confidence.

Hand to a person: every fix (approve, edit, reject); unclear cause; large redesign; failed retry; absent or failing tests; resource limit reached; malformed model output; low-confidence AI-only finding.

Handoff package: rule, severity, confidence, file and line, code evidence, traced cause, patch diff, tests before and after, re-check result, residual risk. Until reviewed the proposal stays unapplied. Approval, edit, rejection and reason are logged.

Review time (team decision): a person reviews within 1 business day. After 1 business day the proposal is flagged "overdue" at the top of the review list. After 5 business days, or if the code changed, it is marked "expired, unapplied" and re-run. MVP sends no reminder and does no escalation; reminders may be added in the pilot. Nothing is ever applied automatically.

### Statuses (team decision)
| Status | Meaning |
| --- | --- |
| `verified_awaiting_approval` | A fix is ready and a person approves |
| `needs_a_person` | The agent can't or mustn't fix it. A `fix_allowed: false` finding gets this status with reason "fix not allowed" (case_06; in case_10 the SECRET is this, the SQLI is `verified_awaiting_approval`) |
| `rejected` | The fix failed after the retry |
| `not_processed` | A limit stopped the run |
No findings at all: `safe_nothing_to_report`.
`totals` (team decision): `found` = findings with proof (file, line, code) = `verified_awaiting_approval` + `needs_a_person` + `rejected` + `not_processed`. Findings dropped for missing proof are logged, not counted. `fixed_and_verified` = `verified_awaiting_approval` count; `rejected`, `needs_a_person` = their own counts; `remaining` = `not_processed` count.

## 6. Run limits (policy settings)
| Limit | Value | Note |
| --- | --- | --- |
| max_retries | 1 | One retry per finding |
| file_cap | 200 | Starting value, revisit after pilot |
| ai_call_cap | 60 | Starting value, revisit after pilot. The console raises it to 150 (and time_cap to 40 minutes) for model runs only: the first live GPT-5 run made 62 calls on 6 of 10 findings and stopped (2026-10-27, owner decision) |
| time_cap | 20 minutes | Starting value, revisit after pilot |
| step_cap | 50 steps | Team decision. One step = one orchestrator-to-agent handoff (job given, agent finishes, result written to shared state). Tool calls inside an agent are not steps; AI calls count against ai_call_cap |
| token_cap | 400,000 in, 60,000 out | Team decision |
| confidence_gate | 0.70 | Starting value, revisit after pilot; AI-alone findings only |

When a cap is hit: stop and hand the rest to a person. Log tokens used on every run; work out cost later. Cost estimates use the framework's x3 overhead (canvas section 15); model prices are "unmeasured" for now.

## 7. Quality bar (canvas section 14; proposed pilot gates)
| Metric | Threshold | Reason |
| --- | --- | --- |
| Findings with file, line, code evidence | 100% | Unsupported findings cannot be reviewed |
| Original-file or out-of-workspace writes | 0 | Any occurrence violates the safety boundary |
| High-severity detection recall | >= 90% | Missing a serious vulnerability is costly |
| Finding precision | >= 85% | Excessive false positives destroy adoption |
| Verified-fix success rate | >= 75% | False confidence is worse than an unresolved finding |
| False-fix rate | <= 5% | Failing patches cannot be labelled verified; above ~1 wrong "verified" in 20, reviewers stop trusting the label |
| Regression-test pass rate for verified fixes | 100% | A fix that fails the tests cannot be labelled verified |
| Human approval rate of verified proposals | >= 70% | Low acceptance suggests poor usefulness or trust |
| Audit-record completeness | 100% | Required for governance and evaluation |

Evidence coverage and zero unsafe actions are non-negotiable. Rollback (team decision): if serious-finding recall drops below 90%, roll back.
Human-time saving: not measured yet; claim no "% saved" until measured in the pilot. Golden set: 11 cases is a quick check only; label all percentages "directional"; grow to about 20 cases before the pilot decision.

## 8. Conventions
- Python 3.11+, standard library plus `jsonschema` only. Ask before adding any other package.
- JSON for all data.
- Every agent output is validated against `schemas/` before handoff.
- Source code and comments enter an agent's input only as a data field, never in its instructions.
- Masking: replace secrets, emails and phone numbers with placeholders before any model call.
- Model and endpoint: settings read from `.env` (or connected in the console), recorded in every run. Providers: OpenAI (GPT), Anthropic (Claude) and Google (Gemini), chosen from the endpoint host by `agents/model_agents.py`. Use fake data only; real code stays blocked until the platform or security owner chooses an endpoint. The console has no consent checkbox: masking of secrets, emails and phone numbers is automatic and cannot be turned off, and the page says what is sent.
- `test_command`: one command per repository, default `python -m unittest discover -s tests`. Exit 0 = pass, other exit = fail, no tests run = "no tests".
- Isolation: for the build, work in a copy with safety checks. A container comes at the pilot.
- Commit after every green step.
- Never edit `golden/` (especially any `expected.json`) or `canvas.md`.
