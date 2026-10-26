# Cost: Security Analyzer Agent

Model: **claude-sonnet-5-5** for all three agents. Written by `python evals/cost_model.py` from `out/cost/measured.json` and `docs/pricing.json`; every figure below is directional (canvas section 14: about one case per type).

> **Token figures are a size proxy** (characters / 4), not counts from the model's tokenizer. Run `python evals/measure_handoffs.py --count-tokens` for the real Sonnet 5.5 count.

> **Not computed: inputs missing in `docs/pricing.json`:**
>
> - `price_input_per_million: price of 1,000,000 input tokens (from the price card)`
> - `price_output_per_million: price of 1,000,000 output tokens (from the price card)`
> - `price_currency: currency of the price card`
> - `engineer_hourly_rate: engineer hourly rate`
> - `rate_currency: currency of the hourly rate`
> - `engineer_hours_per_scan_today: engineer hours spent per scan today (triage, reproduce, fix, re-test, document, review)`

## 1. What one scan takes (measured)

Source: tokens = characters / 4; not measured. 11 scans (golden case_01 to case_11).

- Handoffs per scan: mean **4.1** (min 1, max 6). A typical scan with one fixable finding is 5: audit, baseline tests, investigate, fix, re-check. A safe project is 1; a project with no tests is 2.
- Findings per scan: 1.0.

| Agent | Handoffs | Tool calls | Input tokens | Output tokens |
| --- | ---: | ---: | ---: | ---: |
| Auditor | 1.6 | 3.6 | 2,016 | 406 |
| Investigator | 0.9 | 1.4 | 934 | 131 |
| Fixer & Validator | 1.5 | 2.0 | 1,777 | 207 |
| **Total per scan** | **4.1** | | **4,727** | **744** |

Rules run first and cost no model tokens (the text-pattern rules are code). Only the three agents above call a model.

## 2. Monthly cost

Not computed: model prices are missing (see the top of this file).

## 3. Against today's cost

Not computed: the model prices, engineer rate or hours per scan are missing.

## 4. Still unmeasured

1. **Real model output tokens.** The output tokens here are what the offline stand-ins returned (short JSON). A model also writes explanations, reasoning and longer patches. Run the agents on the model and read `state.counters.tokens`.
2. **Context re-reads.** A model-backed agent that calls tools re-sends its growing context on every turn. The measured input is one pass over the same data, so real input is higher by an unmeasured factor.
3. **Retry, reflection and guardrail overhead.** The x3 is the framework's assumption. The measured retry rate is 0 (the stand-ins do not retry for model reasons). Replace x3 with the measured ratio after the first pilot runs.
4. **Repository size.** The golden projects are 1 to 3 files; real repositories are far larger, and the file cap is 200. Input grows with the files each agent reads.
5. **Findings per scan.** The golden set averages 1.0 per scan. Real scans find more, and the Investigator and Fixer & Validator run once per finding.
6. **Scan volume.** 20 scans per day (and 5 and 100) are the volumes you gave, not measured. Canvas section 15 says to measure repositories scanned per team per month during discovery.
7. **Share of fixes a person must handle, and review time per proposal.** The person's time is not in the model cost and is not measured; no time-saved figure is claimed (AGENTS.md section 7).
8. **Today's hours per scan.** Taken from your input; it is a cost baseline, not a measurement made here.
9. **Smaller model for the Auditor.** Not used in this measurement, so the Auditor's cost is an upper bound.
10. **Prompt caching and batch discounts.** Not modelled; both would lower the real cost.

## 5. Reproduce

```bash
python evals/measure_handoffs.py --count-tokens   # real Sonnet 5.5 token counts (needs AI_MODEL_ENDPOINT in .env and ANTHROPIC_API_KEY)
python evals/cost_model.py                       # writes this file
```
