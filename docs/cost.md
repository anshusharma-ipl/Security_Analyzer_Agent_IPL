# Cost: Security Analyzer Agent

One real scan, measured. GPT-5 ran all three agents on the demo project (`shop_demo`: 10 findings in 28 files), run `run-001` on 2026-10-29. Every figure is from that run or is arithmetic on it. One run is a sample, not an average.

## 1. At a glance

| Measure | Value |
| --- | --- |
| Cost of one scan | **$0.75** |
| Tokens | 236,478 (190,198 input, 46,280 output) |
| AI calls | 81 (limit 150) |
| Steps | 28 (limit 50) |
| Time | 1,143 seconds, about 19 minutes (limit 2,400) |
| Outcome | 7 findings fixed and approved, 3 left to a person |

One finding (F007, command injection) needed a retry: the first fix called an `echo` program that does not exist on Windows, and the second removed the subprocess call.

## 2. Cost by token type

| Token type | Tokens | Rate per 1M | Cost |
| --- | ---: | ---: | ---: |
| Input | 190,198 | $2.00 | $0.38 |
| Output (includes reasoning) | 46,280 | $8.00 | $0.37 |
| **Total** | **236,478** | | **$0.75** |

The rates are assumed, not a quote: tokens and calls are measured, money is calculated from them. Replace the rates with your own price card.

## 3. Cost at volume

22 working days a month, every scan costing what this run cost. The measured run already includes context re-reads and the retry, so no extra multiplier is applied.

| Scans per day | Scans per month | Tokens per month | Cost per month |
| ---: | ---: | ---: | ---: |
| 5 | 110 | 26 million | about $83 |
| 20 | 440 | 104 million | about $330 |
| 100 | 2,200 | 520 million | about $1,650 |

## 4. Work done by each agent

The run recorded token totals only, not tokens per agent or per finding, so no cost split by agent or finding is shown.

| Agent | What it did | Handoffs |
| --- | --- | ---: |
| Auditor | 1 scan and 8 re-checks | 9 |
| Investigator | 10 investigations, one per finding | 10 |
| Fixer and Validator | 1 baseline test run and 8 fix attempts | 9 |

On average a finding cost about $0.075 in tokens ($0.75 over 10 findings), and a verified fix about $0.107 ($0.75 over 7 fixes).

## 5. Efficiency

| Measure | Value |
| --- | --- |
| Cost per verified fix | $0.107 |
| Cost per AI call | $0.009 |
| Cost per file scanned | $0.027 |
| Tokens per finding | 23,648 |
| Output tokens against the cap | 77% (46,280 of 60,000) |
| Time against the cap | 48% (1,143 of 2,400 seconds) |

## 7. What is still unmeasured

- **Reviewer time.** A person approved the fixes, but how long it took was not recorded, so no time-saved figure is claimed.
- **Larger projects.** This run covered 28 files. Tokens grow with the files and context each agent reads.
- **Other models.** Only GPT-5 has run a full scan with token counts. Claude ran through a local bridge; Gemini has only been tested against a mock server. No price comparison is shown, because other models' prices were not verified.
- **Cost today without the agent.** Engineer hours per finding today are not measured. The canvas uses an illustrative 2.5 hours at $60 an hour.
- **Prompt caching and batch discounts.** Not modelled; both would lower the real cost.
- **Scan volume.** 5, 20 and 100 scans a day are planning volumes, not measurements.

The rules scan itself costs no tokens: it is plain code.
