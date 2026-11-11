# PRD: Security Analyzer Agent

**Status:** draft for the capstone review.
**Sources:** `canvas.md` (the design), `AGENTS.md` (team decisions), `schemas/` (the contract), `evals/` (the measurements).
**How to read it:** sections 1 to 3 say what we are building and for whom. Sections 4 to 6 say how it behaves and how safe it is. Sections 7 to 9 say how we know it works, what it costs and when we stop.

## 1. Summary

### The problem
- Security findings pile up, because sorting them, writing a fix and proving the fix works are all manual.
- Engineers lose time, and trust the scanners less.

### What we are building
- An agent team that takes a Python project, its tests and an approved rules file.
- It finds and ranks weak spots, and prepares a tested fix for each one in a temporary copy.
- It hands every fix to a person, who approves, edits or rejects it.
- It never changes the original files, and never commits or deploys.

### Who it is for
- Three to five engineers in a pilot on one non-production repository.
- The security engineer who owns the rules file.

### Why an agent and not a script
- Scanning is exact and stays in code.
- Judgement is the agent's part: can the finding be traced to untrusted input, what is the smallest safe fix, and when to stop and hand over.
- The golden cases show it: `case_01`, `case_05`, `case_07` and `case_11` are all SQL injection, with four different right answers.

### Non-goals
- No AI-based detection rules in the pilot.
- No automatic apply, commit, pull request, deploy or dependency change.
- No language other than Python.
- No claim of time saved until real reviewers have used it.

## 2. User job and success

- **The job:** when a project has security findings, see only proven findings, each with a tested fix, so the safe ones are approved quickly and the time goes to the ones that need a person.
- **Success in the pilot:**
  - at least 30% less human time per scan (to be measured);
  - no unsafe action;
  - a false-fix rate at or below 5%.

## 3. The contract

### 3.1 What goes in

| Input | Rule |
| --- | --- |
| Source folder | One Python project, read only. At most `file_cap` files (default 200). |
| Rules file | `rules.json`, checked against `schemas/rules.schema.json` before anything runs. One security engineer owns it. The agent never edits it. |
| Tests | The project's own test command, run in the temporary copy with a time limit. |
| Limits | Step cap, AI-call cap, token cap, time cap, retries per fix (default 1). |

### 3.2 What comes out

- `report.json` and `report.md` (and `report.html` in the console).
- `decision_log.json` and the final `state.json`.
- `fixes.patch`, if anything was approved.
- Each finding carries:
  - the rule, file and line, with the quoted code as proof;
  - severity and confidence;
  - the traced cause and the diff;
  - test results before and after, and the re-check result;
  - the residual risk.
- Every agent reply is checked against a JSON schema before the orchestrator accepts it.

### 3.3 Roles and tools

| Role | Decides | Tools | Never |
| --- | --- | --- | --- |
| Auditor | Which rule matches are reportable, and their order | `list_files`, `read_file`, `run_security_rules` | Writes anything |
| Investigator | Whether the cause can be traced, and which fix approach suits it, or hand over | `read_file`, `read_code_structure` | Writes anything |
| Fixer and Validator | The patch, and whether to keep, retry once or reject | `apply_patch` (temporary copy only), `run_tests`, `request_recheck` | Sets the final status |
| Orchestrator (plain code) | Order, limits, approvals, status, report | Its own steps | Is a model |

- Agents never call each other.
- Each agent uses only its own tools, through its own MCP profile.
- The shared state has one owner per field.

### 3.4 Autonomy and hand-over

- The agent works alone, only inside the temporary copy.
- It hands over to a person when:
  - it cannot trace the cause;
  - no tests exist;
  - the fix needs a dependency change or a redesign;
  - the retries are used up;
  - a limit is hit;
  - anything looks unsafe.
- A person approves every fix.
- Two owner decisions refine this (`AGENTS.md` section 5):
  - **Unclear cause, in the console:** a finding whose only problem is that no caller is visible still gets a small local fix, marked "cause not traced", for approval. A needed redesign still goes to a person. This is off in the engine and the evals.
  - **Report only:** secret, weak-hash and dependency findings are never patched. The console shows each as a task for the person (rotate the key, use a password hash, raise the pin).

### 3.5 The console

- A local web page, started with `python ui/server.py` or `start.bat`. Settings are on the left and the scan is on the right.
- **Left:** the project (a folder, a .zip or the built-in demo) and the model (OpenAI GPT, Anthropic Claude, Google Gemini or another compatible gateway).
- **Right:**
  - a live list of what each agent is doing;
  - one card per finding, updated in place;
  - **Approve this fix**, **Reject** and **Edit** on each card;
  - a **What was fixed** screen with before and after, the open tasks and the downloads.
- A note says what leaves the computer: nothing without a model; with one, only the masked code the agents read goes to the chosen provider. Masking is automatic.
- Leaving the page does not lose the scan: the console reconnects to it. See `ui/README.md`.

## 4. How safe it is

### 4.1 What can go wrong, and what stops it

| Failure | Likelihood and impact | Guardrail | Where it is proved |
| --- | --- | --- | --- |
| A false fix: labelled verified but wrong | Medium, high | "Verified" is set only by the orchestrator, from passing tests and a clear re-check. A person approves every fix. | `tests/test_decisions.py`; red-team case 14 still breaks it |
| A patch causes a regression | Medium, high | Smallest change, tests green first, human review, nothing applied automatically | `tests/test_decisions.py` |
| Secrets or personal data reach the model vendor | Medium, high | Masking before any model call; a leak scan on the log and report | `tests/test_containment.py`; red-team case 21 (masking gaps remain) |
| Instructions hidden in code steer the model | Medium, medium | Code is data, never instructions; structured replies only; no free tool access | case 09 passes; red-team cases 12 and 13 still break it |
| Tests or patches run something harmful | Low, high | Forbidden commands, path allow-list, temporary copy only, network denied by default | `kill_checks.py`; red-team case 20 still breaks it |
| The model reports problems that are not real | High, medium | A finding must show file, line and code, or it is dropped | `tests/test_decisions.py` |
| The rules file is wrong or altered | Low, high | Schema check; the version is recorded in every report | Step 1 of every run |
| The model changes behaviour after an update | Medium, medium | The model version is recorded; the full benchmark runs on every change | `evals/run_evals.py` |
| The agent changes original files | Low, high | Files fingerprinted before and after; a mismatch stops the run | `kill_checks.py` |

- **Red team:** 8 of 10 attacks still break the system. They are listed on the "Test cases" page with the smallest proposed fix for each. None is fixed yet.

### 4.2 Input guardrails
- The rules file is checked and the file count is capped before anything runs.
- Only the given folder is read; links that leave it are refused.
- Secrets, email addresses and phone numbers become placeholders before any text reaches a model.
- Hostile text inside code is treated as data and logged as `prompt_injection_attempt`.
- Test commands that install packages, commit, push or deploy are refused.

### 4.3 Output guardrails
- Every agent reply must pass its JSON schema.
- A finding without proof (file, line, and the quoted code really at that line) is dropped and logged.
- A patch must apply and still parse.
  - The model-backed Fixer also refuses patches that touch tests, requirements, the rules file or paths outside the copy.
  - The orchestrator does not yet enforce this for every agent (red-team case 20).
- "Verified" is set only by the orchestrator, from test and re-check results.
- The log and report are scanned for unmasked sensitive values before they are written.
- The originals are fingerprinted again at the end; any change stops the run.

### 4.4 Human in the loop
- A review queue holds each proposed fix with its evidence, diff, test results and residual risk.
- A person approves, edits or rejects each one. Rejecting and editing need a reason.
- An edited patch goes through the same tests and re-check before it counts.
- The orchestrator confirms that only the four decision fields were changed.
- Approved fixes become `fixes.patch`, which a person applies.

## 5. Quality bar and where we stand

Two criteria are non-negotiable: **100% evidence coverage** and **zero unsafe workspace actions**. The rest are pilot thresholds.

| Criterion | Required | Offline agents | Live GPT-5 run | Status |
| --- | --- | --- | --- | --- |
| Findings with file, line and code evidence | 100% | 100% | | Met |
| Writes to originals or outside the workspace | 0 | 0 | 0 | Met |
| High-severity detection recall | at least 90% | 100% | | Met |
| Finding precision | at least 85% | 89% | | Met |
| Verified-fix success rate | at least 75% | 80% (8 of 10 cases) | 70% (7 of 10 findings) | Met offline; live is close |
| False-fix rate | at most 5% | 27% (3 of 11 labels wrong) | not measured | Not met |
| Regression-test pass rate for verified fixes | 100% | 100% | 100% | Met |
| Audit-record completeness | 100% | 100% | 100% | Met |
| Human approval rate of verified proposals | at least 70% | | 100% (7 of 7) | Met on one run |

- **What the two columns are:**
  - *Offline agents* are the built-in agents with no model, scored on the 21 golden cases (about one case per type, so directional).
  - *Live GPT-5 run* is one real scan of the demo project on 2026-10-29. It is one run, not a benchmark.
- **The miss to fix:** the false-fix rate. The built-in agents cannot tell `case_11` from `case_01`, and cannot write a multi-file patch. It is the reason to connect a model, and a model-backed run must be scored against this same table before any pilot.
- **Other results:**
  - kill switches: all eight checks pass;
  - tests: 173 pass.

## 6. How we measure

- **Golden dataset:** 21 cases.
  - 11 are the canvas types.
  - 10 are red-team cases (injection in a docstring, a string literal and a README; weak tests; a re-check that blocks a pair; schema-breaking output; unparsable patches; safe-looking code; forbidden writes; masking gaps).
  - Each has an answer key (`expected.json`). The set grows from failed and rejected fixes.
- **Checks in code:** vulnerability present, test outcome, source integrity, workspace boundaries, syntax validity, patch size, evidence completeness, audit completeness.
- **A second model as judge**, only where code cannot decide:
  - three questions per finding: is the cause explanation correct, is the patch the smallest maintainable fix, is the residual-risk note accurate;
  - answers are `yes`, `no` or `unsure`, and never change a status;
  - `evals/judge.py` is built and tested with a stub; no judge model is configured, so there is no live judge result yet;
  - before relying on it, compare it with a person on at least 20 findings.
- **When it runs:**
  - the full benchmark on every prompt, rule or model change;
  - the full regression before release;
  - sampling of approved and rejected fixes during the pilot;
  - an immediate alert on any unsafe action.
- **Commands:** `python evals/run_evals.py` (metrics), `python evals/redteam.py` (ten attacks), `python kill_checks.py --run` (eight kill switches).

## 7. Cost

- **One scan, measured on GPT-5** (10 findings, 28 files):

| Measure | Value |
| --- | --- |
| Cost | $0.75 |
| Tokens | 236,478 (190,198 in, 46,280 out) |
| AI calls | 81 |
| Time | about 19 minutes |
| Outcome | 7 fixed, 3 left to a person |

- **At volume** (22 working days a month):

| Scans per day | Cost per month |
| --- | --- |
| 5 | about $83 |
| 20 | about $330 |
| 100 | about $1,650 |

- The rates used ($2 in and $8 out per million tokens) must be checked against the real price card.
- Reviewer time, larger projects and other models are not measured. See `docs/cost.md` and the Cost page.

## 8. Rollout

- **One non-production repository**, Python, three vulnerability classes (SQL injection, command injection, path traversal).
- **Three to five engineers**, with manual and agent-assisted work compared on the same labelled examples.
- **Human approval** for every fix. No commits, pull requests, deployments or dependency changes.
- **Scale up only when:**
  - all safety gates hold;
  - the benchmark thresholds are met;
  - reviewers accept at least 70% of verified proposals;
  - no regression is traced to an approved proposal;
  - a second team can adopt the same rule format;
  - costs stay below the measured manual-review cost;
  - code-processing and model-provider policies are approved.

## 9. Kill criteria and rollback

### Stop at once if the agent:
- modifies an original file;
- writes outside the temporary copy;
- contacts an endpoint that is not approved;
- exposes an unmasked secret;
- applies a fix without approval;
- fails to write a complete audit log;
- installs or removes a package;
- commits, pushes, merges or deploys.

Each of the eight has an automatic check and a test (`kill_checks.py`).

### Roll back to the previous rules, prompts, model or scan-only mode if:
- high-severity recall falls below the threshold;
- the false-fix rate goes above 5%;
- reviewers reject more than half of the verified proposals across two evaluation cycles;
- model or execution cost goes above the cost of fixing by hand;
- the benchmark drops after a model or prompt change.

Rollback and scale-up details are in `docs/PILOT.md`.
