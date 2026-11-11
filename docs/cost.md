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

## 3. What the same tokens would cost on other models

This takes the tokens the real run used (190,198 in, 46,280 out) and prices them at each provider's published rate. It is a price comparison, not a run: only GPT-5 was actually run.

| Provider | Model | Input per 1M tokens | Output per 1M tokens | Cost of this run's tokens |
| --- | --- | ---: | ---: | ---: |
| OpenAI | gpt-5 (the model used in this run) | $1.25 | $10.00 | **$0.70** |
| Anthropic | Claude Sonnet 5.5 | $2.00 | $10.00 | **$0.84** |
| Google | Gemini 3.8 Flash | $0.75, then $1.50 from 1 Jan 2027 | $3.75, then $7.50 from 1 Jan 2027 | **$0.32**, then **$0.63** |

## 4. Cost at volume

22 working days a month, every scan costing what this run cost. The measured run already includes context re-reads and the retry, so no extra multiplier is applied.

| Scans per day | Scans per month | Tokens per month | Cost per month |
| ---: | ---: | ---: | ---: |
| 5 | 110 | 26 million | about $83 |
| 20 | 440 | 104 million | about $330 |
| 100 | 2,200 | 520 million | about $1,650 |

## 5. What is still unmeasured

- **Reviewer time.** A person approved the fixes, but how long it took was not recorded, so no time-saved figure is claimed.
- **Larger projects.** This run covered 28 files. Tokens grow with the files and context each agent reads.
- **Other models.** Only GPT-5 has run a full scan with token counts. Claude ran through a local bridge; Gemini has only been tested against a mock server. The comparison in section 3 prices GPT-5's tokens at other models' published rates; it is not a measurement of those models.
- **Cost today without the agent.** Engineer hours per finding today are not measured. The canvas uses an illustrative 2.5 hours at $60 an hour.
- **Prompt caching and batch discounts.** Not modelled; both would lower the real cost.
- **Scan volume.** 5, 20 and 100 scans a day are planning volumes, not measurements.

The rules scan itself costs no tokens: it is plain code.
