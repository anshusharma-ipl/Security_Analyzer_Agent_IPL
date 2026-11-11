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

The rates are the ones used for the report; confirm them against your own price card. With prompt caching on input the total would be about $0.56. No batch discount is applied.

## 3. Cost at volume

22 working days a month, every scan costing what this run cost. The measured run already includes context re-reads and the retry, so no extra multiplier is applied.

| Scans per day | Scans per month | Tokens per month | Cost per month |
| ---: | ---: | ---: | ---: |
| 5 | 110 | 26 million | about $83 |
| 20 | 440 | 104 million | about $330 |
| 100 | 2,200 | 520 million | about $1,650 |

## 4. Cost per finding and per agent

The split is estimated from the work each finding and agent needed. The run recorded only the total.

| Finding | Outcome | Estimated cost |
| --- | --- | ---: |
| F001, F002, F003, F005, F006 (SQL injection) | Fixed and approved | $0.075 each |
| F004 (SQL injection, redesign) | Needs a person | $0.038 |
| F007 (command injection) | Fixed on retry | $0.113 |
| F008 (path traversal) | Fixed and approved | $0.075 |
| F009 (secret), F010 (dependency pin) | Needs a person; never auto-fixed | $0.019 each |

| Agent | Work | Estimated tokens | Estimated cost |
| --- | --- | ---: | ---: |
| Auditor | 1 scan and 8 re-checks | about 75,700 | $0.24 |
| Investigator | 10 investigations | about 85,100 | $0.27 |
| Fixer and Validator | 1 baseline run and 8 fix attempts | about 75,700 | $0.24 |

## 5. The same tokens on other models

A price comparison only. A different model would use a different number of tokens and write different fixes, so measure before choosing.

| Model | Input per 1M | Output per 1M | Total | Compared with GPT-5 |
| --- | ---: | ---: | ---: | --- |
| GPT-5 (used) | $2.00 | $8.00 | $0.75 | |
| GPT-5-mini | $0.40 | $1.60 | $0.15 | 5 times cheaper |
| claude-sonnet-5-5 | $3.00 | $15.00 | $1.26 | 1.7 times more |
| claude-haiku-5-5 | $0.80 | $4.00 | $0.34 | 2.2 times cheaper |
| gemini-flash-latest | $0.15 | $0.60 | $0.056 | 13 times cheaper |
| gemini-pro-latest | $1.25 | $5.00 | $0.47 | 1.6 times cheaper |

## 6. Efficiency

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
- **Other models.** Only GPT-5 has run a full scan with token counts. Claude ran through a local bridge; Gemini has only been tested against a mock server.
- **Cost today without the agent.** Engineer hours per finding today are not measured. The canvas uses an illustrative 2.5 hours at $60 an hour.
- **Prompt caching and batch discounts.** Not modelled; both would lower the real cost.
- **Scan volume.** 5, 20 and 100 scans a day are planning volumes, not measurements.

The rules scan itself costs no tokens: it is plain code.
