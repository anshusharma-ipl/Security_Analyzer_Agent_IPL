# UX review of the console and the explainer pages

Two rounds. Round 1 (2026-10-27) was a designer's review from screenshots. Round 2 (2026-10-27) answers feedback from the first live run on a real model (GPT-5 on the demo project), and replaced the console layout. The console described below is the current one.

## Who this is for and what they need to do

Engineers and security engineers who scan a project, read each proposed fix, and decide. The job is: start a scan, understand what was found, judge each fix with confidence, and take away the report and the patch. Everything else is secondary.

## Round 2: what the live run showed, and what changed

| # | What was seen | Why it matters | What changed |
| --- | --- | --- | --- |
| 1 | Settings, the running agents and the findings competed for one column. | The settings are used once; the scan is watched for minutes. | Two columns. Left: the project and the model. Right: the live agent flow, then the findings, then what was fixed. The Run button stays in reach. |
| 2 | The screen flickered while the agents ran. | It looked broken and made the text hard to read. | The old page redrew the whole feed about ten times a second. Now steps are appended and each finding card is replaced only when that finding changed (in a browser check, none of the 13 cards was ever removed). Polling asks only for new steps, and a brief network hiccup retries quietly. |
| 3 | A raw log was the only view of what the agents were doing. | People want to see progress, as they do in a coding assistant. | A step list that grows as work happens (an agent starts, a file is read, the tests pass, the re-check is clear) with the current action and a loader under it. It holds names and counts only, never code. |
| 4 | An "API format" field, and a checkbox "I understand masked code is sent to this endpoint". | The format is a technical detail, and the checkbox is a gate nobody reads. | A provider choice (OpenAI GPT, Anthropic Claude, Google Gemini, or Other) sets the format; model names are suggestions; the key label follows the provider. The checkbox is now a note that says what leaves the computer and what is masked. Masking is automatic and has no switch. |
| 5 | Nearly every finding ended as "needs a person" and nothing was fixed. | The tool looked useless, and nobody could tell why. | See "Why so many needed a person" below. Each finding that still needs a person now has its reason in plain words and a task ("rotate the key", "raise the pin"), instead of an internal message. |
| 6 | No approval moment like a permission prompt. | The approving step is the product. | Each ready fix has **Approve this fix**, **Reject** and **Edit** on its card. A sticky bar counts decisions and enables **Finish**. A **What was fixed** screen follows, with before and after, the open tasks and the downloads. |
| 7 | The demo project looked like only SQL injection. | It hid the rest of what the tool does. | The demo has 13 findings over all six rule types and three safe files, with a button to use it. |
| 8 | Before and After code was cut off at the card edge. | A reviewer could not read the fix. | Code wraps, and Before sits above After when the card is narrow, so every character is visible. |

### Why so many needed a person (found in the first GPT-5 report)

Four separate causes, not one: no visible caller (now proposed anyway for approval, with a warning, as a console default); a bug that rejected an answer when the model gave a cause with no path (fixed); a fix that needed a second file the Fixer could not see (the Fixer now gets the other files on the traced path); and rules that are report-only by decision (secret, weak hash, dependency), which now show as tasks. See `AGENTS.md` section 5.

## Round 1: what was wrong first

| # | Finding | What changed |
| --- | --- | --- |
| 1 | The review was one long scroll. | A review desk in round 1; in round 2 replaced by inline approval on each finding card. |
| 2 | The warning banner was a full-width paragraph. | One short note, in plain words, now in the left column. |
| 3 | Capitals, mixed pill colours and decorative borders competed for attention. | Sentence case. Colour is used only for state: waiting for you, verified, at risk. |
| 4 | The submit button was far from the decisions and always enabled. | A sticky bar shows "2 of 3 decided" and enables **Finish** only when every fix has a decision. |
| 5 | The docs were two very long pages. | A short Guide, a collapsed list of the prompts, and a filterable list of the 21 test cases. |
| 6 | The docs were not reachable from the console. | A top navigation on every page. |
| 7 | Internal terms leaked into the interface ("handoff", "x-owner", "recheck"). | Plain labels such as "Temporary copy", "Your files are unchanged", "Needs your action". |

## Design choices

- **One accent colour** (deep teal) and a calm cool grey ground. Amber means "waiting for you", green means fixed or approved, red means risk.
- **The agent flow** is the distinctive element: a timeline of who is acting and what they are doing, so you always know where the scan is.
- **Typefaces:** Public Sans for text and JetBrains Mono for code.
- **Accessibility:** visible keyboard focus, labels on every input, a light and a dark theme, reduced motion respected, a single column at tablet and phone width with no sideways scrolling.

## Still to do

- Test with real users: can someone who has never seen it finish a review without help?
- Large projects need pagination in the findings list.
- The page cannot reopen a finished scan after a reload (the run and report are kept on the server).
- Gemini has only been tested against a mock server; its first live run is a test.
