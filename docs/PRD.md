# PRD: Security Analyzer Agent

| | |
| --- | --- |
| **Status** | Draft for the capstone review |
| **Sources** | `canvas.md` (the design), `AGENTS.md` (team decisions), `schemas/` (the contract), `evals/` (the measurements) |
| **Reading guide** | 1 and 2: what it is and who it is for. 3: how it works. 4: how it stays safe. 5 and 6: how we know it works. 7 to 9: cost, the pilot and when we stop. |

## 1. Summary

### The problem

Security scanners find problems, but they leave the hard part to people: working out which ones are real, and turning each one into a safe, tested fix. That is still manual work.

- **Long, noisy lists.** Many findings are false alarms or low risk, so engineers spend their time sorting before they fix anything.
- **Scattered context.** To understand one finding, an engineer reads several files, the scan report and tickets.
- **Weak tests.** Passing tests do not prove the weakness is gone, or that the code still behaves the same.

**The result.** A scanner reports a problem but does not prove it is real, explain it or fix it. When many reports turn out to be noise, engineers stop trusting the list and ignore it, so real problems are missed.

### What we are building

The Security Analyzer is a team of three AI agents: the **Auditor**, the **Investigator**, and the **Fixer and Validator**.

- **You give it** a Python project, its tests and an approved rules file.
- **It finds and ranks** the weak spots.
- **It prepares and tests** a fix for each one, in a temporary copy.
- **A person decides.** Every fix is approved, edited or rejected by a person.
- **It never** changes your original files, and it never commits or deploys.

### Who it is for

- **Software engineers who fix security findings alongside their feature work**<br>Why they need it: faster investigation and checking, with enough evidence to approve a fix with confidence, and not another list of possible problems.

### Why an agent and not a script

- **Scanning for weak spots.** It is exact and repeatable, so it needs no judgement.
- **Tracing the cause.** It has to read code across several files to see whether untrusted input can reach the weak spot.
- **Choosing the smallest safe fix.** The right fix differs each time. In the golden set, four SQL injection cases (`case_01`, `case_05`, `case_07`, `case_11`) have four different right fixes.
- **Deciding when to stop and hand over.** Safety depends on knowing what it cannot do.

### Non-goals

- **AI-based detection rules**<br>Findings come only from the approved rules file.
- **Automatic apply, commit, pull request, deploy or dependency change**<br>A person always applies a fix.

## 2. User job and success

### The job

When a project has security findings, the engineer should be able to:

- **See only proven findings,** each with a tested fix.
- **Approve the safe fixes quickly.**
- **Spend their time** on the ones that need a person.

### Success in the pilot

- **At least 30% less human time per scan.**
- **No unsafe action.**
- **A false-fix rate at or below 5%.**

## 3. How it behaves

### 3.1 Inputs

| Input | Rule |
| --- | --- |
| Source folder | One Python project, read only. At most 200 files are scanned. |
| Rules file | `rules.json`, checked against `schemas/rules.schema.json` before anything runs. One security engineer owns it, and the agents never edit it. |
| Tests | The project's own test command (default `python -m unittest discover -s tests`), run in the temporary copy. Each test run is stopped after **120 seconds**; a run that times out cannot verify a fix. |
| Limits | The run limits below. |

### 3.2 Limits and default values

If a limit is reached, the run stops cleanly: findings not yet handled are marked "not processed" and the review queue is still written.

| Limit | Default | What it does |
| --- | --- | --- |
| File cap | 200 files | Lists no more than this many files; the rest are not scanned and the report says so. |
| Step cap | 50 steps | One step is one handoff to an agent. Stops endless loops. |
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

| Role | Decides | Tools |
| --- | --- | --- |
| Auditor | Which rule matches are reportable, and their order | `list_files`, `read_file`, `run_security_rules` |
| Investigator | Whether the cause can be traced, and which fix approach suits it, or hand over | `read_file`, `read_code_structure` |
| Fixer and Validator | The patch, and whether to keep, retry once or reject | `apply_patch` (temporary copy only), `run_tests`, `request_recheck` |
| Orchestrator (plain code) | Order, limits, approvals, status, report | Its own steps |

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

| What can go wrong | What stops it | Stopped when tested? |
| --- | --- | --- |
| A fix is marked verified but is wrong | Only the orchestrator can mark a fix verified, and only after passing tests and a clear re-check | No (red-team case 14) |
| A fix breaks working code | Tests must pass first, and a person reviews every fix | No (red-team case 14) |
| Secrets reach the AI provider | They are replaced by placeholders before any model call | Yes |
| Hidden instructions in code steer the model | Code is read as text and never obeyed, and the attempt is logged | Yes |
| A fix runs something harmful | Forbidden commands are refused, only the temporary copy is written, and a fix may never change the project's tests | Yes |
| The model reports a problem that is not real | A finding with no file, line and code is dropped | Yes |
| The rules file is wrong | It is checked against a schema at the start of every run | Yes |
| An agent sends bad numbers to get around the run limits | A handoff with missing or negative usage numbers is rejected, and the finding goes to a person | Yes |
| Your original files change | They are fingerprinted before and after, and any change stops the run | Yes |
| A fix is applied without a person's approval | Every fix waits in a review queue with its evidence, diff and test results. A person approves, edits or rejects it, and applies the approved fixes (`fixes.patch`) themselves. | Yes |
| The AI provider updates the model and it starts giving different answers | Every run records the model version, so a change can be traced. After a change, the test cases are run again and compared with the earlier results. | By hand (a person has to start the test run) |

**Stopped when tested?** **Yes**: the tests pass and no attack gets through. **No**: a red-team attack beat this guardrail, so open the case to see how. **By hand**: a person has to start the check. Nothing runs it automatically.

The checks come in three kinds. Code tests check that the guardrails work: `tests/test_decisions.py` and `tests/test_containment.py` cover the ones above. `kill_checks.py` checks the eight kill criteria. `evals/run_evals.py` checks how the agents behave on the test cases.

Red team: 7 of 10 attacks held. Three remain (cases 14, 15 and 19), each with its smallest proposed fix on the Evals and testing page.

## 5. Quality bar and where we stand

Two measures must always hold: every finding has evidence, and nothing is written to your original files. The rest are pilot thresholds. **Built-in agents** are the agents with no AI model, scored on the 21 test cases (a direction, not a proof). **Live run** is one real scan with GPT-5.

| Measure | Required | Built-in agents | Live GPT-5 run | Met? |
| --- | --- | --- | --- | --- |
| Every finding has file, line and code evidence | 100% | 100% | 100% (10 of 10) | Yes |
| Writes to your originals or outside the temporary copy | 0 | 0 | 0 | Yes |
| Serious problems found (high-severity recall) | at least 90% | 100% | n/a (no answer key for the demo project) | Yes |
| Findings that are real (precision) | at least 85% | 89% | n/a (no answer key for the demo project) | Yes |
| Fixes that end up verified (verified-fix success) | at least 75% | 80% (8 of the 10 cases that expect a fix) | 70% (7 of 10 findings) | Built-in: yes. Live: close |
| Wrong fixes marked verified (false-fix rate) | at most 5% | 27% (3 of 11 labels wrong) | not measured (a person must check each fix) | No |
| Verified fixes that pass the tests | 100% | 100% | 100% | Yes |
| Complete audit record | 100% | 100% | 100% | Yes |
| Verified fixes that people approve | at least 70% | n/a (no human reviewer) | 100% (7 of 7) | Yes, on one run |

## 6. How we measure

### 6.1 What we score against

| Set | Cases | What it holds |
| --- | ---: | --- |
| Golden dataset | 11 | Realistic small projects, one for each of the 11 situations the canvas lists. Each has an answer key (`expected.json`). |
| Red-team attacks | 10 | Cases written to break the system: instructions hidden in code, weak tests, a re-check that blocks a pair, broken replies, unparsable patches, safe-looking code, forbidden writes, secrets the masking misses. Each has an answer key too. |

The plan is to grow both sets from failed and rejected fixes.

### 6.2 How each result is judged

| Method | Used for | How |
| --- | --- | --- |
| Checks in code | Is the weakness there? Did the tests pass? Are your files unchanged? Did everything stay inside the copy? Does the fix parse? Is the evidence and the audit record complete? | Exact. Pass or fail. |
| A second model as judge | Are the explanation, the fix and the risk note sound? | **Planned, not run yet.** It would never change a status. |

### 6.3 How to run it

Run these by hand after any prompt, rule or model change, and before a release. There is no automatic pipeline yet.

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

### What the pilot is

- **Where:** one non-production repository.
- **What it covers:** Python projects, and three kinds of problem: SQL injection, command injection and path traversal.
- **Who:** three to five engineers. Manual work and agent-assisted work are compared on the same labelled examples.
- **Approval:** a person approves every fix. There are no commits, pull requests, deployments or dependency changes.

### When we scale up

We scale up only when all of these are true:

- All safety gates hold.
- The benchmark thresholds are met.
- Reviewers accept at least 70% of verified proposals.
- No regression is traced to an approved proposal.
- A second team can adopt the same rule format.
- Costs stay below the measured manual-review cost.
- Code-processing and model-provider policies are approved.

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

### Rollback: the product owner decides to go back to the previous rules, prompts, model or scan-only mode if

- High-severity recall falls below the threshold.
- The false-fix rate goes above 5%.
- Reviewers reject more than half of the verified proposals across two evaluation cycles.
- Model or execution cost goes above the cost of fixing by hand.
- The benchmark drops after a model or prompt change.

Rollback and scale-up details are in `docs/PILOT.md`.
