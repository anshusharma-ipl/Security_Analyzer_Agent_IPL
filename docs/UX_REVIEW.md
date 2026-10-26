# UX review of the console and the explainer pages

Reviewed on 2026-10-27 from screenshots at 1440 px and on a phone-width window. Reviewer: Claude, acting as a UX designer. The changes below are in the repository.

## Who this is for and what they need to do

Engineers and security engineers who scan a project, read each proposed fix, and decide. The job is: start a scan, understand what was found, judge each fix with confidence, and take away the report. Everything else is secondary.

## What was wrong

| # | Finding | Why it matters | What changed |
| --- | --- | --- | --- |
| 1 | The review was one long scroll: stepper, review box, findings, trace table and log stacked in one column. | The person decides on one finding at a time, but had to scroll past everything else to reach the decision. | A review desk: findings on the left, the selected finding on the right, with the decision beside the evidence. Handoffs and the decision log moved to their own tabs. |
| 2 | The warning banner was a full-width paragraph of orange text above everything. | It was read once and then ignored, and it pushed the work down. | One short line, kept visible, in plain words. |
| 3 | Labels in capitals ("1 · PROJECT TO SCAN", "STEP 5"), mixed pill colours and decorative borders competed for attention. | Colour should mean something. | Sentence case. Colour is used only for state: waiting for you, verified, at risk. |
| 4 | The submit button was far from the decisions and always enabled. | A person could finish a review without deciding on every fix. | A sticky bar shows "2 of 3 decided" and enables **Finish review** only when every fix has a decision. |
| 5 | Model settings (endpoint, key, agents, acknowledgement) were a long form in the left column. | Most people never touch them. | A compact Agents panel. The form opens on demand. |
| 6 | The docs were two very long pages. The prompts page showed the prompt, the output, two columns and a checklist for every step at once, on a dense, sidebar-heavy layout. | Nobody could see the shape of the project. | A short Guide, a collapsed list of the fifteen prompts, and a filterable list of the 21 test cases. Detail opens on demand. |
| 7 | The docs were not reachable from the console. | The person who runs a scan could not find the explanation. | A top navigation on every page, and contextual links ("How to connect a model"). |
| 8 | Several internal terms leaked into the interface ("handoff", "x-owner", "recheck"). | They mean nothing to a new user. | Plain labels: "Temporary copy", "Originals intact?", "You decide". Internal terms stay in the Handoffs tab. |

## Design choices

- **One accent colour** (deep teal) and a calm cool grey ground. Amber means "waiting for you", green means verified, red means risk.
- **The pipeline strip** is the one distinctive element: seven steps on a single line, so you always know where the scan is and who is acting.
- **Typefaces:** Public Sans for text and JetBrains Mono for code. Body text stays under about 70 characters a line.
- **Accessibility:** visible keyboard focus, labels on every input, a light and a dark theme, reduced-motion respected, layout works at phone width.

## Still to do

- Test with real users: can someone who has never seen it finish a review without help?
- The diff view is unified only. A side-by-side view would help with larger patches.
- Large projects need pagination in the findings list.
