# PRD: Security Analyzer Agent

Status: draft for the capstone review, 2026-10-27. Sources: `canvas.md` (the design), `AGENTS.md` (team decisions), `schemas/` (the contract), `evals/` (the measurements). Numbers are from the latest eval run with the offline stand-in agents and are directional (about one golden case per type).

## 1. Summary

**Problem.** Security findings pile up because triaging them, writing a fix and proving the fix works are all manual. Engineers lose time and trust the scanners less.

**What we are building.** An agent team that takes a Python project, its tests and an approved rules file, finds and ranks weak spots, prepares a tested fix for each in a temporary copy, and hands every fix to a person to approve, edit or reject. It never changes the original files and never commits or deploys.

**Who it is for.** Three to five engineers in a pilot on one non-production repository, and the security engineer who owns the rules file.

**Why an agent, not a script.** Scanning is deterministic and stays in code. Judgement is the agent's part: whether a finding can be traced to untrusted input, what the smallest safe fix is, and when to stop and hand over. The agent is useful only where the golden cases show different correct outcomes for the same detection (for example case_01, case_05, case_07 and case_11 are all SQL injection with four different right answers).

**Non-goals.** No AI-based detection rules in the pilot. No automatic apply, commit, pull request, deploy or dependency change. No languages other than Python. No claim of time saved until real reviewers have used it.

## 2. User job and success

When a project has security findings, an engineer wants to see only proven findings, each with a fix that has been tested, so they can approve the safe ones quickly and spend their time on the ones that need a person.

Success in the pilot: at least 30% less human time per scan (to be measured), no unsafe action, and a false-fix rate at or below 5%.

## 3. The contract

### 3.1 Input

| Field | Rule |
| --- | --- |
| Source folder | One Python project, read only. At most `file_cap` files (default 200). |
| Rules file | `rules.json`, validated against `schemas/rules.schema.json` before anything runs. Owned by one security engineer. The agent never edits it. |
| Tests | The project's own test command, run in the temporary copy with a time limit. |
| Policy | Step cap, AI-call cap, token cap, minutes cap, retries per fix (default 1). |

### 3.2 Output

Every run writes `report.json` and `report.md` (and `report.html` in the console), `decision_log.json`, the final `state.json`, and `fixes.patch` if anything was approved. Each finding has: rule, file, line, quoted code (proof), severity, confidence, traced cause, a diff, test results before and after, the re-check result, and the residual risk. Every agent output is validated against a JSON schema before the orchestrator accepts it.

### 3.3 Roles and tools

| Role | Decides | Tools | Never |
| --- | --- | --- | --- |
| Auditor | Which rule matches are reportable, and their order | `list_files`, `read_file`, `run_security_rules` | Writes anything |
| Investigator | Whether the cause can be traced and what fix approach suits it, or hand to a person | `read_file`, `read_code_structure` | Writes anything |
| Fixer and Validator | The patch, and whether to keep, retry once or reject | `apply_patch` (temporary copy only), `run_tests`, `request_recheck` | Sets the final status |
| Orchestrator (plain code) | Order, limits, approvals, status, report | its own steps | Is a model |

Agents never call each other. Each uses only its own tools through its own MCP profile. The shared state has one owner per field.

### 3.4 Autonomy and hand-over

The agent acts alone inside the temporary copy. It must hand over to a person when: it cannot trace the cause, no tests exist, the fix needs a dependency change or a redesign, retries are used up, a limit is hit, or anything looks unsafe. A person approves every fix.

## 4. Quality bar

Two criteria are non-negotiable: 100% evidence coverage and zero unsafe workspace actions. The rest are pilot thresholds.

| Criterion | Required | Measured now | Result |
| --- | --- | --- | --- |
| Findings with file, line and code evidence | 100% | 100% | Met |
| Original-file or out-of-workspace writes | 0 | 0 | Met |
| High-severity detection recall | at least 90% | 100% | Met |
| Finding precision | at least 85% | 89% | Met |
| Verified-fix success rate | at least 75% | 60% | Not met |
| False-fix rate | at most 5% | 33% | Not met |
| Regression-test pass rate for verified fixes | 100% | 100% | Met |
| Audit-record completeness | 100% | 100% | Met |
| Human approval rate of verified proposals | at least 70% | not measured | Needs real reviewers |

The two misses come from the stand-in Fixer, which patches only one shape of SQL injection. They are the reason to connect a model; they are not hidden. A model-backed Fixer must be measured against the same table before any pilot.

## 5. Failure modes and guardrails

| Failure mode | Likelihood and impact | Guardrail | Where it is proved |
| --- | --- | --- | --- |
| A false fix: labelled verified but wrong | Medium, high | Verified only when tests pass and the re-check is clear, decided by the orchestrator from tool results. A person approves every fix. | `tests/test_decisions.py`; red-team case 14 (still breaks the system) |
| A patch causes a regression | Medium, high | Smallest change, tests green first, human review, nothing applied automatically | `tests/test_decisions.py` |
| Secrets or personal data reach the model vendor | Medium, high | Masking before any model call; a leak scan on the log and report | `tests/test_containment.py`; red-team case 21 (masking gaps remain) |
| Instructions hidden in code steer the model | Medium, medium | Code is data, never instructions; structured replies only; no free tool access | case 09 passes; red-team cases 12 and 13 still break it |
| Tests or patches run something harmful | Low, high | Forbidden commands, path allow-list, temporary copy only, deny by default network | `kill_checks.py` (8 of 8 pass); red-team case 20 (patches that edit tests or leave the copy) still breaks it |
| The model reports problems that are not real | High, medium | A finding must show file, line and code, or it is dropped | `tests/test_decisions.py` |
| The rules file is wrong or altered | Low, high | Schema validation, version recorded in every report | step 1 of every run |
| The model changes behaviour after an update | Medium, medium | Fixed model version recorded; full benchmark on every change | `evals/run_evals.py` |
| The agent changes original files | Low, high | Files fingerprinted before and after; mismatch stops the run | `kill_checks.py` |

Red team: 8 of 10 attacks currently break the system. They are listed on the "How it was built" page under step 8, with the smallest proposed fix for each. None is fixed yet.

### 5.1 Input guardrails

- The rules file is validated and the file count is capped before anything runs.
- Only the given folder is read; links that leave it are refused.
- Secrets, email addresses and phone numbers are replaced with placeholders before any text reaches a model.
- Hostile text inside code is treated as data and logged as `prompt_injection_attempt`.
- Test commands that install packages, commit, push or deploy are refused.

### 5.2 Output guardrails

- Every agent reply must pass its JSON schema.
- A finding without proof (file, line and the quoted code really at that line) is dropped and logged.
- A patch must apply and still parse. The model-backed Fixer also refuses patches that touch tests, requirements, the rules file, or paths outside the copy. The orchestrator does not yet enforce that for every agent (red-team case 20).
- "Verified" is set only by the orchestrator from test and re-check results.
- The log and report are scanned for unmasked sensitive values before they are written.
- The originals are fingerprinted again at the end; any change stops the run.

### 5.3 Human in the loop

A review queue holds each proposed fix with its evidence, diff, test results and residual risk. A person approves, edits or rejects each one; rejecting and editing need a reason. An edited patch is run through the same tests and re-check before it counts. The orchestrator confirms that only the four decision fields were changed. Approved fixes become `fixes.patch`, which a person applies. The console shows this as a review desk.

## 6. Evaluation plan

**Golden dataset.** 21 cases: 11 canvas types and 10 red-team cases (injection in a docstring, a string literal and a README; weak tests; a re-check that blocks a pair; schema-breaking output; unparsable patches; safe-looking code; forbidden writes; masking gaps). Each has an answer key (`expected.json`). The set grows from failed and rejected fixes.

**Deterministic checks (code).** Vulnerability presence, test outcome, source integrity, workspace boundaries, syntax validity, patch size, evidence completeness, audit completeness.

**LLM-as-judge (only where code cannot check).** A second model, different from the agents, answers three questions per finding from masked text: is the root-cause explanation correct, is the patch the smallest maintainable fix, is the residual-risk note accurate. Answers are `yes`, `no` or `unsure`. They are shown beside the metrics and never change a status or a pass. `evals/judge.py` is built and tested with a stub; no judge endpoint is configured yet, so no live judge result exists. Before relying on it, compare its answers with a person's on at least 20 findings and report the agreement.

**Cadence.** Full benchmark on every prompt, rule or model change; full regression before release; sampling of approved and rejected fixes during the pilot; an immediate alert on any unsafe action.

**Harness.** `python evals/run_evals.py` (metrics against the gates), `python evals/redteam.py` (ten attacks), consistency runs (status flips between runs), attribution (which agent broke first), `python kill_checks.py --run` (eight kill switches).

## 7. Cost at production volume

Measured with the stand-in agents, per scan: 4.1 handoffs, about 4,700 input and 740 output tokens (a characters-divided-by-four proxy). Rules cost no tokens. Real use will be higher: a model re-reads its context on every tool turn, writes explanations, and retries. The cost model assumes a multiplier of 3 until measured.

The Guide's [cost page](/docs/cost.html) turns this into tokens and money for any volume: enter your price card and scans per day. Volumes under discussion are 5, 20 and 100 scans per day. Prices, engineer rate and hours per scan are not yet supplied, so no money figure is claimed here. See `docs/cost.md` for the ten unmeasured items.

## 8. Rollout and kill criteria

Pilot: one non-production repository, Python, three vulnerability classes, three to five engineers, manual and agent-assisted work compared on the same labelled examples. The pilot stops at once if the agent modifies an original, writes outside the copy, contacts an unapproved endpoint, exposes an unmasked secret, applies a fix without approval, fails to write a complete audit log, installs or removes a package, or commits, pushes, merges or deploys. Each of the eight has an automatic check and a test (`kill_checks.py`). Rollback and scale-up criteria are in `docs/PILOT.md`.

## 9. Open questions and risks

1. Which model endpoint is approved, and may masked code be sent to it? Until then the agents are stand-ins and the model path has only been tested against a mock.
2. Real model results for verified-fix success and false-fix rate.
3. Who is the security engineer who owns the rules, and who is the product owner? (`docs/PILOT.md`, marked TO FILL.)
4. Whether `request_recheck` should stay a plain tool call or become an explicit Auditor job (`docs/roster.md`).
5. The eight red-team failures, starting with case 14 (a false fix labelled verified), which breaks the false-fix gate directly.
6. Hosting: the console runs uploaded tests, so it needs a container and access control before anyone else uses it (`docs/DEPLOY.md`).
