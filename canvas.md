# Agent Opportunity Canvas: Security Analyzer Agent

*Security Analyzer Agent · IPL Neural Navigators · Cohort ICAIPM2026F*

**Team members:** Anshu, Archana, Bikash

## The canvas at a glance

| A · WHY | B · WHAT | C · HOW SAFE | D · HOW WE KNOW |
| --- | --- | --- | --- |
| **Posture:** it finds problems, prepares tested fixes and shows they work, but a person always decides what is applied | **Trigger:** a person starts it on a code folder, for example before a release or after an audit finding | **Human review:** a person approves every fix, and is also called in whenever the agent cannot decide | **Quality bar:** precision ≥ 85%, high-severity recall ≥ 90%, verified-fix success ≥ 75%, false-fix rate ≤ 5%, 100% evidence coverage, zero unsafe actions |
| **Problem:** security findings pile up because sorting them, fixing them and proving the fix are all manual work | **Tools:** 7 agent tools (read files, run security rules, read code structure, apply a fix, run tests, request a re-check) | **Main risks:** a wrong fix, code or secrets leaving the company, instructions hidden in code, running untrusted code | **Cost:** to be measured |
| **Outcome:** at least 30% less human time per scan, and a report of what was found and fixed as proof | **Steps:** scan, investigate, fix, verify, then a person approves | **Safeguards:** sensitive data is hidden before anything goes to the AI model, every fix is tested, every decision is logged | **Pilot:** one non-production repository, one language, three vulnerability classes, 3–5 engineers |
| **Agents:** Auditor, Investigator, Fixer & Validator, plus a workflow orchestrator that is not an agent | **Design:** three agents with separate jobs, coordinated by the workflow orchestrator | **Never allowed:** changing original files, committing or deploying code, sending secrets to the model | **Stop rule:** stop at once if the agent ever touches an original file or writes outside its temporary copy |

---

## A · WHY: the opportunity

### 1. Agent name, owner and posture

| Item | Answer |
| --- | --- |
| **Agent name** | Security Analyzer Agent |
| **Business owner** | Business owner responsible for engineering/application-security outcomes |
| **Product owner** | The product manager. Owns the specification, the default rules and the quality thresholds, and decides whether to roll back |
| **Posture, in one line** | A fix-and-prove agent, not an auto-merge agent. It identifies policy-defined code risks, investigates their causes, prepares minimal fixes in an isolated copy, verifies them, and presents the evidence to a human reviewer. |

### 2. Users and context

| Item | Answer |
| --- | --- |
| **Primary user** | Software engineer responsible for resolving application-security findings within a development team |
| **Secondary users** | Application-security engineers, code reviewers, engineering managers, release managers, and audit or compliance teams |
| **Context signals** | A release or merge is approaching; a security scan has generated findings; an audit issue or security ticket has been raised |
| **Key reality** | Developers will not trust the system unless original code remains unchanged, sensitive code is protected, every finding includes evidence, and every fix is reviewable and reversible |

**Primary persona: Meera**
- Software engineer responsible for resolving application-security.
- Receives lengthy scanner reports without clear remediation priorities.
- Spends time reproducing findings, tracing causes, making repetitive fixes, and proving that the changes are safe.
- Needs a ranked, evidence-backed list of findings and small, tested fixes that she can review.

### 3. The problem, reframed

| Item | Answer |
| --- | --- |
| **Surface framing** | Teams say "we need a better scanner" or "developers need more security training" |
| **Actual problem** | Existing scanners identify possible risks but leave the expensive work of prioritization, investigation, remediation, regression testing, and evidence collection to engineers. |
| **Today's process** | An engineer runs a scanner or waits for an audit, reads the results, decides what to fix first, fixes items one at a time, then reruns the tests and the scan |
| **What breaks today** | Serious problems get buried in long lists, fixes are delayed, rushed fixes can break working features, and there is no before-and-after evidence |

### 4. Job to be done

**As a** senior engineer who is responsible for security in my team, **I need to** know what is genuinely risky in my code and get safe, tested fixes, **so that** I can release without leaving security problems behind and can show progress.

**The agent's job, in one sentence:** *"Given a source-code folder, its automated tests and an approved security-rules file, the Security Analyzer agent finds and ranks the places that break the rules, investigates their causes and prepares tested fixes in a safe copy, without modifying the original files and without applying an unapproved change."*

### 5. Outcomes, value and non-goals

| Metric | Baseline today | Target | How we measure it |
| --- | --- | --- | --- |
| **Human time per scan** (main measure) | Measure during pilot| At least 30% lower than manual flow | Compare manual and agent-assisted completion on the same benchmark |
| **Finding precision** | Measure on benchmark | ≥ 85% | Expert-confirmed findings ÷ all reported findings |
| **High-severity finding recall** | Measure on benchmark | ≥ 90% | Correctly detected high-severity cases ÷ labelled high-severity cases |
| **Verified-fix success rate** | Measure on benchmark | ≥ 75% | Fixes that remove the issue, preserve expected behavior, and pass tests |
| **False fix rate** | Measure on benchmark | ≤ 5% | Fixes labelled verified where the issue remains or behavior is incorrect |
| **Evidence coverage** | Not applicable | 100% | Every finding contains rule, file, line, and relevant code evidence |
| **Unsafe actions** | 0 | 0 | Workspace and file-integrity monitoring |

**Value type:** ☑ time saved ☑ quality improved ☑ Security risk reduced ☑ new capability (verified evidence of what was found and fixed) ☑ cost reduced

**Explicit non-goals:**

The first version will not:
- Modify original source files.
- Commit, push, merge, deploy, or open pull requests.
- Install or remove packages.
- Delete files.
- Autonomously apply fixes outside the temporary workspace.
- Perform large architectural redesigns.
- Replace penetration testing, threat modelling, code review, or an organization’s security program.
- Evaluate or rank developers.
- Generate security rules without security-engineer ownership.

### 6. Why agentic? (and why not)

| Agentic Need | ☑ / ✗ (Required?) | Why (Evidence) |
| --- | --- | --- |
| Multi-step reasoning | ☑ | The next action depends on finding confidence, root cause, fixability, tests, and re-scan results. |
| Tool use | ☑ | It must read code, invoke rules, inspect code structure, apply patches, run tests, and re-scan. |
| Persistent context across sessions | ✗ for MVP | Run-level context is sufficient; organizational learning comes through rules and benchmark updates. |
| Variable inputs | ☑ | Repositories differ in structure, coding patterns, dependencies, and data flows |
| Sufficient Volume | ☑ to validate | Security review repeats across releases and repositories |
| Bounded autonomy | ☑ | It can analyze and patch only inside an isolated temporary workspace |
| Independent verification | ☑ | The component writing a fix should not be the sole judge of its success |

**Why not a simpler scanner solution?**
A scanner can identify rule matches, but it does not necessarily:
- establish whether a finding is meaningful in its code context;
- trace how unsafe input reaches a sensitive operation;
- select a context-appropriate remediation;
- prepare and undo a patch;
- run regression tests;
- independently re-check whether the issue is resolved;
- assemble an approval-ready evidence package.

**Where a person must always decide:**
- whether a proposed fix is accepted;
- whether a fix is applied to the real codebase;
- whether a large redesign is undertaken;
- whether dependencies are added or removed;
- whether rules or severity levels are changed;
- what happens when tests are absent or unreliable;
- what happens when the root cause cannot be confidently determined.

---

## B · WHAT: the agent

### 7. Triggers and channels

| Item | Proposed entry |
| --- | --- |
| **Triggers** | Manual scan before release or merge; response to a security ticket; response to an audit finding |
| **Primary Channels** | Internal chat-style or web interface |
| **Secondary output channels** | Downloadable patch file, machine-readable results, security report, and audit log |
| **Channel constraints** | One project per run; one supported programming language in the MVP; human reviewer must be available; English-only interface initially |

### 8. Inputs, knowledge and data

| Source | What the agent uses it for | Owner | How fresh | Sensitivity |
| --- | --- | --- | --- | --- |
| Source-code folder | Scan and contextual investigation | Engineering team | Read at the start of each run | Confidential; may contain secrets or test PII |
| The rules file (`rules.json`) | Checks, severity, fix eligibility, and remediation guidance | application-security function or designated security owner | Version-controlled and checked at the start of each run | Internal |
| Existing automated tests | Regression verification | Engineering team | Current repository version and Run during each run | Internal |
| Test execution command | Determines how validation runs | Engineering team | Per repository | Internal |
| Policy settings |File, step, token, time, and retry limits | Product owner | Version-controlled | Internal |
| Model endpoint configuration | Controls approved inference environment | designated platform or security owner | Deployment configuration | Sensitive configuration |
| Benchmark dataset | Regression evaluation | Product and security owners | Updated after reviewed failures | Confidential |

**Consent and data minimisation.** Processing is permitted only for source code the organization is authorized to analyze. Applicable privacy, confidentiality, contractual, data-classification, and approved AI-provider requirements must be satisfied before processing.

**What the agent often cannot know.** It cannot tell how the code is deployed, whether a problem can really be reached in production, or whether the tests cover the behaviour it changed. When it is unsure, it says "unverified" instead of "fixed", shows the evidence it has, and hands the case to a person.

### 9. Tools and actions

A **tool** is something an agent chooses to use while it works. The workflow orchestrator's own steps are listed separately, because the agents do not choose them and cannot skip them.

**Agent tools (7)**

| Tool | Used by | What it does | Reads or changes? | Who approves its use | If it fails |
| --- | --- | --- | --- | --- | --- |
| `list_files` | Auditor | Lists the project's files, skipping folders such as version control and installed packages, up to the file cap | Reads only | The user, by choosing the folder | Stops and explains why |
| `read_file` | Auditor, Investigator | Reads one source file | Reads only | The user, by choosing the folder | Skips the file and notes it |
| `run_security_rules` | Auditor | Runs the text-pattern security rules from the rules file on the files | Reads only | The security engineer, by writing the rule | Skips a faulty rule and notes it |
| `read_code_structure` | Investigator | Reads how the code is built (functions and what calls what) to trace how bad input reaches a weak spot | Reads only | Built in | Hands the case to a person |
| `apply_patch` | Fixer & Validator | Applies a fix to the temporary copy, checks that the changed files are still valid code, and undoes the change if they are not | Changes the temporary copy only | The rule's fix setting, then a person | Undoes the change |
| `run_tests` | Fixer & Validator | Runs the project's own tests in the temporary copy | Runs the tests; changes nothing | The project team, which owns the tests and the test command | The fix is not called verified, and a person is told |
| `request_recheck` | Fixer & Validator | Asks the Auditor to run the rules again on the changed files and return the result | Reads only (the Auditor uses its own tools) | Built in | The fix is not called verified |

**Workflow steps (run by the workflow orchestrator, not chosen by any agent)**

| Step | When | What it does | If it fails |
| --- | --- | --- | --- |
| Validate the rules file | At the start | Checks that `rules.json` is valid and loads the rules | Stops with a clear message |
| Create the temporary copy | Before any fix | Makes the temporary copy of the project that fixes are tried in | Stops the run |
| Ask a person to approve | After each fix passes its checks | Shows the fix with its evidence in the agent interface and waits for the person to approve, edit or reject | The fix stays unapplied |
| Enforce the limits | Throughout | Caps on files, AI calls, time and retries; hands the case to a person when a cap is reached | Stops the run |
| Check the originals are unchanged | At the end | Confirms that the original files were not changed | Stops the run and raises an alert |
| Write the decision log | Throughout | Records every decision made by the agents and the workflow orchestrator | Stops the run, because decisions must always be logged |
| Write the report | At the end | Builds the report (with the totals) and the patch file from the results the agents recorded | Writes a partial report |

**The agent may do these on its own:** read files, run the rules, investigate, rank the findings, prepare and test fixes in the temporary copy, undo a failed fix, retry once, and write the report.

**The agent must never:** change the original files; commit, push, merge or deploy; apply a fix without approval; send code anywhere except the AI model service; send secrets unhidden; edit the rules file; add or remove software packages; or delete files.

### 10. Decision loop and architecture

**Perceive → Decide → Act → Learn**

- **Perceive:** reads the rules, the code, the scan findings, and the test and re-check results.
- **Decide:** the Auditor decides which findings have enough evidence. The Investigator decides how a problem arises and which fix suits it. The Fixer & Validator decides whether to keep, retry or reject a fix, based on the tests and the Auditor's re-check.
- **Act:** writes the smallest fix that works in the temporary copy, runs the tests, asks the Auditor to re-check, asks a person to approve, and writes the report.
- **Learn:** every decision is logged. Rejected or undone fixes are added to the benchmark, and the rules and prompts are improved over time. The AI model is not retrained.

**For each finding, the agents decide in this order:**

1. No proof (file, line and code)? Drop the finding.
2. Needs a big redesign, or the cause is unclear? Stop and ask a person.
3. The rule's fix setting is off? Report the problem but do not fix it.
4. Otherwise prepare a fix in the temporary copy and test it. If the tests pass and the re-check is clear, a person approves it. If not, the agent retries once; if it fails again, the fix is rejected and listed in the report with the evidence.

**Patterns used:** ☑ pipeline ☑ routing ☑ parallelisation ☑ reflection ☑ tool use ☐ MCP ☐ planning ☑ multi-agent

**Single or multi-agent?** Multi-agent: three agents plus a workflow orchestrator. Finding, explaining and fixing are different jobs with different cost and risk, and the agent that writes a fix does not decide alone whether it worked: the project's tests and the Auditor's re-check decide that.

| Agent | What it does | If it fails | Why an agent, not a tool |
| --- | --- | --- | --- |
| Auditor | Applies all the rules to the whole project and ranks the findings | Nothing is found, so the run stops | AI-based rules and ranking need judgement; only its text search is a plain tool |
| Investigator | Works out how bad input reaches one weak spot | Fixes would be guesses, so a person takes over | Following data across the code is reasoning, not a lookup |
| Fixer & Validator | Writes the fix, runs the tests, asks the Auditor to re-check, and decides to keep, retry or reject | Nothing is verified, so nothing is called fixed | Deciding from test results needs judgement; running the tests is a plain tool |

**Three-sentence test for each agent.** Sentence 1 says what the agent decides; sentence 2 says what it chooses between and from what evidence; sentence 3 says what breaks if it were a plain tool call. An agent that fails the test becomes a tool call.

| Agent | Sentence 1: what it decides | Sentence 2: what it chooses between, and from what | Sentence 3: what breaks as a plain tool call | Verdict |
| --- | --- | --- | --- | --- |
| **Auditor** | It decides which findings have enough evidence to be reported and in what priority order. | It chooses between keeping, dropping and ranking each candidate finding, using the rule match, the surrounding code and the AI-based rules. | A scan tool would still return text-pattern matches, but it could not judge AI-based rules or rank findings by context, so engineers would be back to a long unsorted list. | **Passes, narrowly.** Its text search (`run_security_rules`) is already a tool. It stays an agent only while AI-based rules and ranking are in scope. If the pilot used text-pattern rules only, collapse it into that tool plus a sort. |
| **Investigator** | It decides how untrusted input reaches one weak spot and which kind of fix suits that path. | It chooses between fix approaches and between "fixable" and "hand to a person", using the code structure and the files it reads. | A lookup cannot follow data across several files or decide when the cause is unclear, so fixes would be guesses. | **Passes.** |
| **Fixer & Validator** | It decides whether a fix is kept, retried once or rejected. | It chooses between those outcomes using the test results and the Auditor's re-check, not its own opinion of its patch. | Running tests is a plain tool, but reading mixed test and re-check results and deciding keep, retry or reject needs judgement. | **Passes.** |

**Limits on each run:** one retry per finding, and caps on files, AI calls and time (values to be identified).

**Architecture sketch:**

```mermaid
flowchart TD
    IN["Inputs<br/>code folder, tests, rules.json"] --> ORCH
    PERSON["Person<br/>approves, edits or rejects each fix"] <--> ORCH
    ORCH["Workflow orchestrator (not an agent)<br/>order, limits, approvals, decision log, report"]

    ORCH --> AUD["1. Auditor<br/>finds and ranks findings<br/><br/>list_files, read_file, run_security_rules"]
    ORCH --> INV["2. Investigator<br/>traces the cause, picks a fix approach<br/><br/>read_file, read_code_structure"]
    ORCH --> FIX["3. Fixer and Validator<br/>fixes, tests, keeps / retries / rejects<br/><br/>apply_patch, run_tests, request_recheck"]

    AUD --> SRC[("Source files<br/>read-only")]
    FIX --> TMP[("Temporary copy")]

    AUD --> LLM["AI model service<br/>sees code with sensitive values hidden"]
    INV --> LLM
    FIX --> LLM

    ORCH --> OUT["Report, patch file, audit log"]
```

Every hand-off goes through the workflow orchestrator; the agents never call each other.

### 11. Outputs and the I/O contract

```
Input:  { source_folder, rules_file, policy { file_cap, max_retries, test_command } }
Output: { totals { found, fixed_and_verified, rejected, needs_a_person, remaining },
          findings[ { rule_id, file, line, severity, evidence, confidence, detected_by,
                      status, patch_diff, tests, recheck } ],
          approvals, audit_log }
```

**Required for trust and audit (not just engineering preferences):** `evidence` (file, line and quoted code), `confidence`, `detected_by` (a rule or the AI model), `status`, `recheck`, `approvals` and `audit_log`. The report also records the rules-file version, the AI model and its version, and how many sensitive items were hidden.

---

## C · HOW SAFE: Trust

### 12. Human-in-the-loop design

| Item | Proposed entry |
| --- | --- |
| **Pattern** | A person approves every fix before it leaves the temporary copy, and the agent also hands over any case it cannot decide |
| **Human triggers** | Every fix; unclear cause; large redesign; failed retry; absent or failing tests; resource limit reached; malformed model output; low-confidence AI-only finding |
| **Handoff package** | Rule, severity, confidence, file and line, code evidence, traced cause, patch diff, tests before and after, re-check result, and residual risk |
| **Human SLA** | Define during pilot; until reviewed, the proposal remains unapplied |
| **Feedback** | Approval, edit, rejection, and reason are logged; reviewed failures become benchmark cases. |

### 13. Risks, failure modes and guardrails

**Spec line:** **Zero** writes to original files or outside the temporary copy, and **zero** unmasked secrets sent to the model, in every run; the number is zero because a single occurrence breaks the trust condition engineers set for using the tool at all, and a miss means a security incident, an immediate stop of the pilot and lost reviewer trust.

| Risk or failure mode | Likelihood | Impact | What protects us (Guardrail) |
| --- | --- | --- | --- |
| A false fix: the agent says it fixed the problem, but it did not, or the fix is wrong | M | H | Verified only if the tests pass and the re-check is clear. A person approves every fix, and we track the false-fix rate |
| Patch creates an undetected regression | M | H | Smallest possible change, tests green before we start, a person reviews every change, nothing applied automatically |
| Secrets or personal data reach the AI vendor | M | H | Data masking, local processing where possible, approved private endpoint |
| Instructions hidden in code comments try to steer the AI model | M | M | Treat code as untrusted data; structured model output; no direct model tool access |
| The tests or the changes run something harmful | L | H | Isolated container, restricted filesystem, no credentials, network deny-by-default |
| The AI model reports problems that are not real | H | M | A finding must show its file, line and code, or it is dropped |
| The rules file is wrong or has been tampered with | L | H |Version control, integrity validation, version recorded in every report |
| The AI model changes behaviour after a vendor update | M | M | The model version is fixed, and the benchmark is re-run on every change |
| Agent changes original files | L | H | Read-only mount, file-integrity check, immediate stop and alert |

**Input safeguards:** reads only the given folder, caps the number of files, checks the rules file, hides secrets and personal data before anything goes to the AI model, and treats code as data, never as instructions.

**Output safeguards:** model replies must follow a strict format; every finding shows its file, line and code; changed files must still be valid code; a fix is "verified" only when the tests pass and the re-check is clean; the original files are checked to be unchanged.

**Regulation and policy** (legal review needed):

- **India's DPDP Act, 2023:** applies if the code or test data holds personal data. Send as little as possible to the AI vendor, hide personal data, and have data-processing terms with the vendor.
- **Sector rules (for example RBI) and customer contracts:** regulated or confidential code may not be allowed to go to an outside AI vendor. Get compliance sign-off, or use a private model endpoint.
- **SOC 2 and ISO 27001** (security standards companies are audited against): not required of the product, but the report and decision log can serve as evidence of secure development.
- Internal secure-development and data-classification policies.

**Accountability:** the engineer who approves a fix owns that change. The product owner owns the agent's behaviour, its false-fix rate and the rollback decision. The business owner owns the outcomes.

---

## D · HOW WE KNOW: proof and cost

### 14. Evaluation and quality bar

Two criteria are non-negotiable: 100% evidence coverage and zero unsafe workspace actions. The other thresholds are proposed for the pilot.

**Spec line:** **False-fix rate ≤ 5%** of fixes labelled verified, because every fix is human-reviewed and above roughly 1 wrong "verified" label in 20 reviewers stop trusting the label; a miss means a reviewer approves a fix that leaves the hole open, the team believes it is closed, and the risk ships unnoticed. *(Proposed rationale, to confirm on the pilot benchmark. With about 20 verified fixes, one error already equals 5%, so treat the figure as directional until the set is larger.)*

**Proposed pilot quality gates**

| Quality criterion | Proposed Threshold | Rationale (Why it matters) |
| --- | --- | --- |
| **Findings with file, line, and code evidence** | 100% | Unsupported findings cannot be reviewed |
| **Original-file or out-of-workspace writes** | 0 | Any occurrence violates the safety boundary |
| **High-severity detection recall** | ≥ 90% | Missing a serious vulnerability is costly |
| **Finding precision** | ≥ 85% | Excessive false positives destroy adoption |
| **Verified-fix success rate** | ≥ 75% | False confidence is worse than an unresolved finding |
| **False-fix rate** | ≤ 5% | Failing patches cannot be labelled verified |
| **Regression-test pass rate for verified fixes** | 100% | A fix that fails the tests cannot be labelled verified |
| **Human approval rate of verified proposals** | ≥ 70% | Low acceptance suggests poor usefulness or trust |
| **Audit-record completeness** | 100% | Required for governance and evaluation |

**Golden dataset**
Start with the minimum: **11 deliberately vulnerable examples, one per type below**, and grow the set as failed or rejected fixes are reviewed. With one example per type the thresholds cannot be measured yet, so early results are directional. Types to include:
- SQL injection.
- Command injection.
- Path traversal.
- Safe code that resembles vulnerable code.
- Multi-file source-to-sink paths.
- Cases requiring dependency changes.
- Cases requiring architectural redesign.
- Missing and failing tests.
- Prompt-injection-like comments.
- Secrets and personal data in test fixtures.
- Cases in which the correct decision is to stop and escalate.

**Evaluation methods**
Use deterministic evaluation for:
- vulnerability presence;
- test outcomes;
- source-file integrity;
- workspace boundaries;
- syntax validity;
- patch size;
- evidence completeness.

Use expert review for:
- whether the vulnerability is genuine;
- whether the root-cause explanation is correct;
- whether the patch is minimal and maintainable;
- whether residual risk is represented correctly.

**Evaluation cadence**
- Full benchmark for every prompt, rule, or model change.
- Full regression evaluation before release.
- Sample approved and rejected fixes during the pilot.
- Immediate alert for any unsafe action.
- Track precision, recall, false-fix rate, retry rate, approval rate, time, and cost per run.

### 15. Cost and feasibility

| Item | Proposed framing |
| --- | --- |
| **Volume** | To measure repositories scanned per team per month during discovery |
| **Tokens per run** (text the AI reads and writes) | To measure separately for scanning, investigation, and fixing |
| **Which model for which step (Model strategy)** | To use deterministic rules first; use a smaller approved model for finding classification and prioritization; reserve the stronger model for root-cause analysis and patch drafting |
| **Monthly cost** | To calculate after measuring repository size, findings per run, context size, retry rate, and model selection; include ×3 overhead as required by the framework |
| **Cost today without the agent** | The Engineering hours spent triaging, reproducing, fixing, re-testing, documenting, and reviewing findings |
| **Feasibility** | **Data:** the code is local, but a security engineer must write the first rules file. **Tools:** all exist (text search, code-structure reader, test runner, temporary workspaces, AI model service). **Biggest technical risk:** the AI model reporting problems that are not real, and fixes that pass weak tests but are wrong. **Biggest adoption risk:** many projects lack tests anyone can trust |

### 16. Rollout and kill criteria

**Proposed pilot**
- One secure, nonproduction sample repository.
- One programming language.
- Three vulnerability classes: SQL injection, command injection, and path traversal.
- One security engineer who owns rules.json.
- Three to five engineer participants.
- Human approval for every proposed fix.
- No commits, pull requests, deployments, or dependency modifications.
- Compare manual and agent-assisted remediation on the same labelled examples.

**Scale-up criteria**
Expand only when:
- all safety gates remain satisfied;
- benchmark thresholds are met;
- human reviewers accept at least 70% of verified proposals;
- no regression is attributed to an approved agent proposal during the pilot;
- the second team can adopt and maintain the same rule format;
- costs remain below the measured manual-review cost;
- code-processing and model-provider policies are approved.

**Immediate kill criteria**
Stop the system immediately if it:
- modifies an original file;
- writes outside the temporary workspace;
- contacts an unauthorized network endpoint;
- exposes an unmasked secret;
- applies a fix without approval;
- fails to create a complete audit log;
- installs or removes a package;
- performs a commit, push, merge, or deployment.

**Operational rollback criteria**
Roll back to the previous rules, prompts, model, or deterministic scan-only mode if:
- high-severity recall falls below the agreed threshold;
- the false-fix rate exceeds 5%;
- reviewers reject more than half of verified proposals across two evaluation cycles;
- model or execution cost exceeds manual remediation cost;
- benchmark performance drops after a model or prompt change.

**Biggest assumption to test first**
Existing project tests, combined with an independent security re-check and human review, are strong enough for engineers to trust the proposed fixes.

**Security Analyzer Agent is a multi-agent fix-and-prove system that checks source code against organization-owned security rules, investigates evidence-backed risks, prepares minimal fixes in an isolated copy, validates them through tests and an independent re-check, and leaves every real code change under human control.**