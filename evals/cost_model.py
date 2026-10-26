"""Cost model (canvas section 15): monthly model cost against the cost of doing the work by hand today.

    python evals/cost_model.py

Reads   out/cost/measured.json   (from evals/measure_handoffs.py: handoffs and tokens per agent per scan)
        docs/pricing.json         (YOUR inputs: model prices, engineer rate, hours per scan today)
Writes  docs/cost.md

No number is invented. A price, rate or hours value left as null in docs/pricing.json is listed as missing, and the
cost sections that need it are written as "not computed" instead of guessed.

Model: every agent runs on claude-sonnet-5-5 (the measurement scope you chose). The canvas strategy would put the
Auditor's classification on a smaller approved model, so the Auditor line here is an upper bound.
Monthly model cost = scans per day x days per month x tokens per scan x price x overhead multiplier (x3, canvas section 15).
Cost today = scans per day x days per month x engineer hours per scan x hourly rate.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEASURED = os.path.join(ROOT, "out", "cost", "measured.json")
PRICING = os.path.join(ROOT, "docs", "pricing.json")
OUT = os.path.join(ROOT, "docs", "cost.md")
AGENTS = (("auditor", "Auditor"), ("investigator", "Investigator"), ("fixer_validator", "Fixer & Validator"))
REQUIRED = {
    "price_input_per_million": "price of 1,000,000 input tokens (from the price card)",
    "price_output_per_million": "price of 1,000,000 output tokens (from the price card)",
    "price_currency": "currency of the price card",
    "engineer_hourly_rate": "engineer hourly rate",
    "rate_currency": "currency of the hourly rate",
    "engineer_hours_per_scan_today": "engineer hours spent per scan today (triage, reproduce, fix, re-test, document, review)",
}
TEMPLATE = {
    "model": "claude-sonnet-5-5",
    "price_input_per_million": None, "price_output_per_million": None, "price_currency": None,
    "engineer_hourly_rate": None, "rate_currency": None, "engineer_hours_per_scan_today": None,
    "fx_rate_rate_currency_per_price_currency": None,
    "overhead_multiplier": 3, "days_per_month": 30, "scans_per_day": [5, 20, 100],
    "note": "Fill the null values. fx_rate is only needed when the two currencies differ.",
}


def missing_inputs(pricing: dict) -> list[str]:
    missing = [f"{key}: {why}" for key, why in REQUIRED.items() if pricing.get(key) in (None, "")]
    if (pricing.get("price_currency") and pricing.get("rate_currency")
            and pricing["price_currency"] != pricing["rate_currency"] and not pricing.get("fx_rate_rate_currency_per_price_currency")):
        missing.append("fx_rate_rate_currency_per_price_currency: the two currencies differ, so the exchange rate is needed")
    return missing


def per_scan(measured: dict) -> dict:
    """Mean handoffs and tokens per scan, per agent and in total, from measured.json."""
    agents = measured["summary"]["per_agent"]
    return {"handoffs": measured["summary"]["handoffs_per_scan"]["mean"],
            "in": sum(agents[a]["in_tokens"] for a, _ in AGENTS), "out": sum(agents[a]["out_tokens"] for a, _ in AGENTS),
            "agents": agents}


def costs(scan: dict, pricing: dict) -> dict | None:
    """Model cost per scan (before and after overhead) and monthly cost per volume. None while a price is missing."""
    if missing_inputs(pricing):
        return None
    base = (scan["in"] * pricing["price_input_per_million"] + scan["out"] * pricing["price_output_per_million"]) / 1_000_000
    fx = pricing.get("fx_rate_rate_currency_per_price_currency") or 1
    per_scan_model = base * pricing["overhead_multiplier"]
    rows = []
    for volume in pricing["scans_per_day"]:
        scans = volume * pricing["days_per_month"]
        model_cost = per_scan_model * scans
        today = pricing["engineer_hours_per_scan_today"] * pricing["engineer_hourly_rate"] * scans
        rows.append({"scans_per_day": volume, "scans_per_month": scans, "model_cost": model_cost,
                     "today_cost": today, "model_cost_in_rate_currency": model_cost * fx})
    return {"base_per_scan": base, "per_scan_with_overhead": per_scan_model, "rows": rows, "fx": fx}


def money(value: float, currency: str) -> str:
    return f"{value:,.2f} {currency}"


UNMEASURED = [
    "**Real model output tokens.** The output tokens here are what the offline stand-ins returned (short JSON). A model also writes "
    "explanations, reasoning and longer patches. Run the agents on the model and read `state.counters.tokens`.",
    "**Context re-reads.** A model-backed agent that calls tools re-sends its growing context on every turn. The measured input is one "
    "pass over the same data, so real input is higher by an unmeasured factor.",
    "**Retry, reflection and guardrail overhead.** The x3 is the framework's assumption. The measured retry rate is 0 (the stand-ins "
    "do not retry for model reasons). Replace x3 with the measured ratio after the first pilot runs.",
    "**Repository size.** The golden projects are 1 to 3 files; real repositories are far larger, and the file cap is 200. Input grows with "
    "the files each agent reads.",
    "**Findings per scan.** The golden set averages 1.0 per scan. Real scans find more, and the Investigator and Fixer & Validator run "
    "once per finding.",
    "**Scan volume.** 20 scans per day (and 5 and 100) are the volumes you gave, not measured. Canvas section 15 says to measure "
    "repositories scanned per team per month during discovery.",
    "**Share of fixes a person must handle, and review time per proposal.** The person's time is not in the model cost and is not measured; "
    "no time-saved figure is claimed (AGENTS.md section 7).",
    "**Today's hours per scan.** Taken from your input; it is a cost baseline, not a measurement made here.",
    "**Smaller model for the Auditor.** Not used in this measurement, so the Auditor's cost is an upper bound.",
    "**Prompt caching and batch discounts.** Not modelled; both would lower the real cost.",
]


def build(measured: dict, pricing: dict) -> tuple[str, list[str]]:
    """The text of docs/cost.md and the list of missing inputs."""
    scan, missing = per_scan(measured), missing_inputs(pricing)
    result = costs(scan, pricing)
    counted = measured.get("model") is not None
    lines = ["# Cost: Security Analyzer Agent", "",
             f"Model: **{pricing.get('model', 'claude-sonnet-5-5')}** for all three agents. Written by `python evals/cost_model.py` from "
             "`out/cost/measured.json` and `docs/pricing.json`; every figure below is directional (canvas section 14: about one case per type).", ""]
    if not counted:
        lines += ["> **Token figures are a size proxy** (characters / 4), not counts from the model's tokenizer. Run "
                  "`python evals/measure_handoffs.py --count-tokens` for the real Sonnet 5.5 count.", ""]
    if missing:
        lines += ["> **Not computed: inputs missing in `docs/pricing.json`:**", ">"] + [f"> - `{m}`" for m in missing] + [""]

    lines += ["## 1. What one scan takes (measured)", "",
              f"Source: {measured.get('token_source') or measured.get('proxy')}. {measured['summary']['scans']} scans (golden case_01 to case_11).", "",
              f"- Handoffs per scan: mean **{scan['handoffs']:.1f}** (min {measured['summary']['handoffs_per_scan']['min']}, "
              f"max {measured['summary']['handoffs_per_scan']['max']}). A typical scan with one fixable finding is 5: audit, baseline tests, "
              "investigate, fix, re-check. A safe project is 1; a project with no tests is 2.",
              f"- Findings per scan: {measured['summary']['findings_per_scan']:.1f}.", "",
              "| Agent | Handoffs | Tool calls | Input tokens | Output tokens |", "| --- | ---: | ---: | ---: | ---: |"]
    for key, label in AGENTS:
        a = scan["agents"][key]
        lines.append(f"| {label} | {a['handoffs']:.1f} | {a['tool_calls']:.1f} | {a['in_tokens']:,.0f} | {a['out_tokens']:,.0f} |")
    lines += [f"| **Total per scan** | **{scan['handoffs']:.1f}** | | **{scan['in']:,.0f}** | **{scan['out']:,.0f}** |", "",
              "Rules run first and cost no model tokens (the text-pattern rules are code). Only the three agents above call a model.", ""]

    lines += ["## 2. Monthly cost", ""]
    if result is None:
        lines += ["Not computed: model prices are missing (see the top of this file).", "",
                  "## 3. Against today's cost", "", "Not computed: the model prices, engineer rate or hours per scan are missing.", ""]
    else:
        pc, rc = pricing["price_currency"], pricing["rate_currency"]
        lines += [f"Per scan: {money(result['base_per_scan'], pc)} before overhead, **{money(result['per_scan_with_overhead'], pc)}** after the "
                  f"x{pricing['overhead_multiplier']} overhead for retries, reflection and guardrails. "
                  f"Month = {pricing['days_per_month']} days.", "",
                  f"| Scans per day | Scans per month | Model cost per month ({pc}) | Cost today per month ({rc}) |",
                  "| ---: | ---: | ---: | ---: |"]
        for r in result["rows"]:
            lines.append(f"| {r['scans_per_day']} | {r['scans_per_month']:,} | {r['model_cost']:,.2f} | {r['today_cost']:,.2f} |")
        lines += ["", "## 3. Against today's cost", "",
                  f"Today: {pricing['engineer_hours_per_scan_today']} engineer hours per scan at {money(pricing['engineer_hourly_rate'], rc)} per hour = "
                  f"{money(pricing['engineer_hours_per_scan_today'] * pricing['engineer_hourly_rate'], rc)} per scan.", "",
                  "| Scans per day | Model cost per month | Cost today per month | Model cost as share of today's cost |",
                  "| ---: | ---: | ---: | ---: |"]
        for r in result["rows"]:
            share = r["model_cost_in_rate_currency"] / r["today_cost"] * 100 if r["today_cost"] else float("nan")
            lines.append(f"| {r['scans_per_day']} | {money(r['model_cost_in_rate_currency'], rc)} | {money(r['today_cost'], rc)} | {share:.1f}% |")
        lines += ["", "This compares model cost only. A person still reviews every fix, and that time is not in the model cost (see section 4). "
                      "No saving in engineer time is claimed.", ""]

    lines += ["## 4. Still unmeasured", ""] + [f"{n}. {item}" for n, item in enumerate(UNMEASURED, 1)]
    lines += ["", "## 5. Reproduce", "", "```bash", "python evals/measure_handoffs.py --count-tokens   # real Sonnet 5.5 token counts (needs AI_MODEL_ENDPOINT in .env and ANTHROPIC_API_KEY)",
              "python evals/cost_model.py                       # writes this file", "```", ""]
    return "\n".join(lines), missing


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if not os.path.isfile(MEASURED):
        print("out/cost/measured.json is missing. Run: python evals/measure_handoffs.py", file=sys.stderr)
        return 2
    with open(MEASURED, encoding="utf-8") as handle:
        measured = json.load(handle)
    if not os.path.isfile(PRICING):
        os.makedirs(os.path.dirname(PRICING), exist_ok=True)
        with open(PRICING, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(TEMPLATE, handle, indent=2)
            handle.write("\n")
        print("created docs/pricing.json with blanks for you to fill")
    with open(PRICING, encoding="utf-8") as handle:
        pricing = {**TEMPLATE, **json.load(handle)}
    text, missing = build(measured, pricing)
    with open(OUT, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print(f"wrote docs/cost.md ({'complete' if not missing else 'partial'})")
    for m in missing:
        print(f"  missing: {m}")
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
