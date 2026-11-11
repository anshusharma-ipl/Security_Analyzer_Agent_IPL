"""Copy the per-agent result of the last eval into docs_html/data/attribution.json, for the Evals page and the Agent design page.

    python evals/run_evals.py                 # writes out/evals/last_eval.json
    python docs_html/collect_attribution.py

Kept: which cases ran, the stage where each failing case first showed up, and the plain reason. Nothing else is copied.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "evals"))

import attribution  # noqa: E402


def main() -> int:
    with open(os.path.join(ROOT, "out", "evals", "last_eval.json"), encoding="utf-8") as handle:
        ev = json.load(handle)
    out = {
        "ai_model": ev["ai_model"]["name"],
        "repeats": ev["repeats"],
        "cases_run": [c["case"] for c in ev["cases"]],
        "failing": {stage: [{"case": x["case"], "why": x["first"]["why"]} for x in ev["attribution"].get(stage, [])] for stage in attribution.ORDER},
        "judged_on": {stage: sorted({why for why_stage, why in list(attribution.CHECK_OWNER.values()) + [o for _, o in attribution.EXTRA_PREFIX] if why_stage == stage}) for stage in attribution.ORDER},
    }
    with open(os.path.join(HERE, "data", "attribution.json"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(out, handle, indent=1)
        handle.write("\n")
    print("attribution.json:", {s: len(v) for s, v in out["failing"].items()}, "of", len(out["cases_run"]), "cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
