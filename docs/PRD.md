# PRD: Security Analyzer Agent

| | |
| --- | --- |
| **Status** | Draft for the capstone review |
| **Sources** | `canvas.md` (the design), `AGENTS.md` (team decisions), `schemas/` (the contract), `evals/` (the measurements) |
| **Reading guide** | Sections 1 and 2: what and for whom. Section 3: how it behaves. Section 4: how safe it is. Sections 5 and 6: how we know it works. Sections 7 to 9: cost, rollout and when we stop. |

## 1. Summary

### The problem

Application-security scanners produce long lists of findings. Turning a finding into a safe, tested fix is still manual work.

| Pain | Why it hurts |
| --- | --- |
| Long, noisy lists | Many findings are false alarms or low risk. Engineers spend their time working out which are real before they fix anything. |
| Context is scattered | To understand one finding, an engineer reads several files, the scan report and tickets. |
| Weak tests | A passing test run does not prove the weakness is gone or that behaviour is unchanged. |
| Repeated explanations | The same investigation is written up again for the security engineer and the code reviewer. |

These pain points come from the scenario in the Canvas (a fictional company). They are hypotheses to validate in the pilot, not measurements.

**Why trust in scanners falls.** A scanner reports a problem but does not prove it is real, does not explain it and does not fix it. When many reports turn out to be noise, engineers stop believing the list and start ignoring it, so real issues are missed.

### What we are building

An agent team that takes a Python project, its tests and an approved rules file. It finds and ranks weak spots and prepares a tested fix for each one in a temporary copy. It hands every fix to a person, who approves, edits or rejects it. It never changes the original files and never commits or deploys.

### Who it is for

| Who | Need |
| --- | --- |
| Software engineers who resolve security findings and write the fixes alongside feature work (the canvas persona is Meera) | Faster investigation and verification, with the evidence needed to approve a fix confidently. Not another list of possible problems. |
| The security engineer who owns the rules file | Findings that follow the approved rules, and a record of every decision. |

The pilot has three to five engineers on one non-production repository.

### Why an agent and not a script

| Part of the work | Done by | Reason |
| --- | --- | --- |
| Scanning for weak spots | Code | Exact and repeatable. No judgement needed. |
| Tracing whether a finding is reachable from untrusted input | Agent | Needs reading code across files. |
| Choosing the smallest safe fix | Agent | The right answer differs by case. In the golden set `case_01`, `case_05`, `case_07` and `case_11` are all SQL injection with four different right answers. |
| Deciding when to stop and hand over | Agent, with code rules | Safety depends on knowing what it cannot do. |

### Non-goals

| Not in scope | Meaning |
| --- | --- |
| AI-based detection rules | Findings come only from the approved rules file. |
| Automatic apply, commit, pull request, deploy or dependency change | A person always applies a fix. |

## 2. User job and success

| | |
| --- | --- |
| **The job** | When a project has security findings, see only proven findings, each with a tested fix, so the safe ones are approved quickly and the time goes to the ones that need a person. |
| **Success in the pilot** | At least 30% less human time per scan (to be measured), no unsafe action, and a false-fix rate at or below 5%. |

## 3. How it behaves

### 3.1 Inputs

| Input | Rule |
| --- | --- |
| Source folder | One Python project, read only. At most 200 files are scanned. |
| Rules file | `rules.json`, checked against `schemas/rules.schema.json` before anything runs. One security engineer owns it. The agent never edits it. |
| Tests | The project's own test command (default `python -m unittest discover -s tests`), run in the temporary copy. Each test run is stopped after **120 seconds**; a run that times out cannot verify a fix. |
| Limits | The run limits below. |

### 3.2 Limits and default values

If a limit is reached, the run stops cleanly: findings not yet handled are marked "not processed" and the review queue is still written.

| Limit | Default | What it does |
| --- | --- | --- |
| File cap | 200 files | Lists no more than this many files; the rest are not scanned and the report says so. |
| Step cap | 50 steps | One step is one handoff to an agent. Stops runaway loops. |
| AI-call cap | 60 calls | Counts every model request. The console raises it to 150 for runs with a model. |
| Token cap | 400,000 in and 60,000 out | Stops spending on a single scan. |
| Time cap | 20 minutes | Stops a scan that takes too long. The console raises it to 40 minutes for runs with a model. |
| Test time limit | 120 seconds per test run | Stops a hanging test suite. |
| Retries per fix | 1 | If a fix fails its tests or re-check, one more attempt is allowed, then it goes to a person. |
| Confidence gate | 0.70 | A finding reported by the AI model with less than 70% confidence goes to a person. Findings from the rules are not affected. |

### 3.3 Outputs

Every run writes these files.

| File | What it holds |
| --- | --- |
| `report.md` / `report.html` | The readable report: each finding, its evidence, the fix and the result. `report.html` is the version shown in the console. |
| `report.json` | The same report as data, for other tools. |
| `review_queue.json` | The fixes waiting for a person to approve, edit or reject. |
| `decision_log.json` | Every decision with its time and who made it (an agent, the orchestrator or a person). |
| `state.json` | The final shared state of the run, including counters for steps, AI calls and tokens. |
| `fixes.patch` | The approved fixes as one patch, only if something was approved. A person applies it. |

### 3.4 What each finding carries

Every finding in the report has the same fields, so a reviewer can decide without searching.

| Field | What it shows |
| --- | --- |
| Rule, file, line | What was found and where. |
| Quoted code | The exact line, as proof. A finding without proof is dropped. |
| Severity and confidence | How serious it is, and how sure the finder is. A rule match carries a fixed confidence of 0.90; only a finding the model reports itself carries a model-judged value. |
| Traced cause | Where the untrusted input comes from, or why that could not be traced. |
| Diff | The proposed change. |
| Tests before and after | Whether the project's tests passed before the change and after it. |
| Re-check | Whether the rules, run again on the fixed copy, still find the problem. |
| Residual risk | What the fix does not cover. |

Every agent reply is checked against a JSON schema before the orchestrator accepts it.

### 3.5 Roles and tools

| Role | Decides | Tools | Never |
| --- | --- | --- | --- |
| Auditor | Which rule matches are reportable, and their order | `list_files`, `read_file`, `run_security_rules` | Writes anything |
| Investigator | Whether the cause can be traced, and which fix approach suits it, or hand over | `read_file`, `read_code_structure` | Writes anything |
| Fixer and Validator | The patch, and whether to keep, retry once or reject | `apply_patch` (temporary copy only), `run_tests`, `request_recheck` | Sets the final status |
| Orchestrator (plain code) | Order, limits, approvals, status, report | Its own steps | Is a model |

Agents never call each other. Each agent uses only its own tools. The shared state has one owner per field.

### 3.6 When the agent hands over to a person

A person approves every fix. In addition, the agent stops and hands a finding over in the situations below.

| Situation | What happens |
| --- | --- |
| It cannot trace the cause | Handed to a person. (The console still prepares a small local fix for approval, marked "cause not traced".) |
| No tests exist | Handed over. Without tests a fix cannot be verified. |
| The fix needs a redesign or a dependency change | Handed over. |
| Retries are used up, a limit is hit, or anything looks unsafe | Handed over. |
| The finding is a secret, a weak hash or an unpinned dependency | Reported only. Never patched. The console shows each as a task for the person. |

## 4. How safe it is

### 4.1 What can go wrong, and what stops it

| Failure | Likelihood, impact (team estimate) | Guardrail | Where it is proved |
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

Red team: 8 of 10 attacks still break the system. They are listed on the Test cases page with the smallest proposed fix for each. None is fixed yet.

### 4.2 Guardrails by stage

| Stage | Guardrails |
| --- | --- |
| Input | The rules file is checked and the file count is capped before anything runs. Only the given folder is read; links that leave it are refused. Secrets, email addresses and phone numbers become placeholders before text reaches a model. Hostile text in code is treated as data and logged as `prompt_injection_attempt`. Test commands that install packages, commit, push or deploy are refused. |
| Output | Every agent reply must pass its JSON schema. A finding without proof is dropped and logged. A patch must apply and still parse. "Verified" is set only by the orchestrator. The log and report are scanned for unmasked sensitive values. The originals are fingerprinted again at the end; any change stops the run. The model-backed Fixer refuses patches that touch tests, requirements, the rules file or paths outside the copy; the orchestrator does not yet enforce this for every agent (red-team case 20). |
| Human review | Each proposed fix sits in a review queue with its evidence, diff, test results and residual risk. A person approves, edits or rejects it; rejecting and editing need a reason. An edited patch goes through the same tests and re-check. Approved fixes become `fixes.patch`, which a person applies. |

## 5. Quality bar and where we stand

Two criteria are non-negotiable: **100% evidence coverage** and **zero unsafe workspace actions**. The rest are pilot thresholds. Offline agents are the built-in agents with no model, scored on the 21 golden cases (about one case per type, so a direction, not a proof). The live run is one real scan with GPT-5.

| Criterion | Required | Offline agents | Live GPT-5 run | Status |
| --- | --- | --- | --- | --- |
| Findings with file, line and code evidence | 100% | 100% | 100% (10 of 10) | Met |
| Writes to originals or outside the workspace | 0 | 0 | 0 | Met |
| High-severity detection recall | at least 90% | 100% | n/a | Met |
| Finding precision | at least 85% | 89% | n/a | Met |
| Verified-fix success rate | at least 75% | 80% (8 of 10 cases) | 70% (7 of 10 findings) | Met offline; live is close |
| False-fix rate | at most 5% | 27% (3 of 11 labels wrong) | not measured | Not met |
| Regression-test pass rate for verified fixes | 100% | 100% | 100% | Met |
| Audit-record completeness | 100% | 100% | 100% | Met |
| Human approval rate of verified proposals | at least 70% | n/a | 100% (7 of 7) | Met on one run |

**Reading the blank cells.**

| Entry | Meaning |
| --- | --- |
| n/a | The number does not apply. Recall and precision score the deterministic rules. All 10 live findings were found by those rules, not by the model, and the demo project has no answer key, so they are scored on the golden set. Offline runs have no human reviewer, so there is no approval rate. |
| not measured | The number could be measured but was not. The live false-fix rate needs a person to check each approved fix independently. |
| Verified-fix success and "9 of 11 golden cases pass" | Different counts. Verified-fix success counts only the cases where a fix was expected. The golden pass count includes cases where the right answer is to hand over to a person. |

## 6. How we measure

### 6.1 What we score against

| Item | Detail |
| --- | --- |
| Golden dataset | 21 cases. 11 are the canvas types. 10 are red-team attacks. Each has an answer key (`expected.json`). The plan is to grow the set from failed and rejected fixes. |
| Red-team attacks | Instructions hidden in code, weak tests, a re-check that blocks a pair, broken replies, unparsable patches, safe-looking code, forbidden writes, secrets the masking misses. |

### 6.2 How each result is judged

| Method | Used for | How |
| --- | --- | --- |
| Checks in code | Vulnerability present, test outcome, source unchanged, files inside the workspace, valid syntax, patch size, evidence and audit completeness | Exact. Pass or fail. |
| A second model as judge | Whether the explanation, the patch and the risk note are sound | **Planned, not run yet.** It never changes a status. |

### 6.3 When it should run

Today the evals are run by hand; there is no automated pipeline yet.

| Trigger | Run |
| --- | --- |
| Any prompt, rule or model change | The full benchmark |
| Before a release | The full regression |
| During the pilot | A sample of approved and rejected fixes |
| Any unsafe action | An immediate alert |

### 6.4 Commands

| Command | What it does |
| --- | --- |
| `python evals/run_evals.py` | Runs all cases and prints each metric against its threshold. |
| `python evals/redteam.py` | Runs the ten attacks and reports which were stopped and which broke the system. |
| `python kill_checks.py --run` | Runs the eight kill-switch checks. |

## 7. Cost

### One scan, measured on GPT-5 (10 findings, 28 files)

| Measure | Value |
| --- | --- |
| Cost | $0.75 |
| Tokens | 236,478 (190,198 in, 46,280 out) |
| AI calls | 81 |
| Time | about 19 minutes |
| Outcome | 7 fixed, 3 left to a person |

### At volume (22 working days a month)

| Scans per day | Scans per month | Cost per month |
| --- | --- | --- |
| 5 | 110 | about $83 |
| 20 | 440 | about $330 |
| 100 | 2,200 | about $1,650 |

The rates used ($2 per million input tokens, $8 per million output tokens) must be checked against the real price card. Reviewer time, larger projects and other models are not measured. See `docs/cost.md` and the Cost page.

## 8. Rollout

| Item | Pilot setting |
| --- | --- |
| Repository | One non-production repository |
| Language and classes | Python; SQL injection, command injection, path traversal |
| People | Three to five engineers; manual and agent-assisted work compared on the same labelled examples |
| Approval | A person approves every fix. No commits, pull requests, deployments or dependency changes. |

**Scale up only when:**

| Condition |
| --- |
| All safety gates hold |
| The benchmark thresholds are met |
| Reviewers accept at least 70% of verified proposals |
| No regression is traced to an approved proposal |
| A second team can adopt the same rule format |
| Costs stay below the measured manual-review cost |
| Code-processing and model-provider policies are approved |

## 9. Kill criteria and rollback

### Kill criteria: stop at once if the agent

- modifies an original file;
- writes outside the temporary copy;
- contacts an endpoint that is not approved;
- exposes an unmasked secret;
- applies a fix without approval;
- fails to write a complete audit log;
- installs or removes a package;
- commits, pushes, merges or deploys.

Each of the eight has an automatic check and a test (`kill_checks.py`).

### Rollback: go back to the previous rules, prompts, model or scan-only mode if

| Trigger |
| --- |
| High-severity recall falls below the threshold |
| The false-fix rate goes above 5% |
| Reviewers reject more than half of the verified proposals across two evaluation cycles |
| Model or execution cost goes above the cost of fixing by hand |
| The benchmark drops after a model or prompt change |

Rollback and scale-up details are in `docs/PILOT.md`.
