"""The judge: a second model, used ONLY for what code cannot check (canvas section 14, expert review).

Code checks everything else: evidence, status, rule, file, line, tests, re-check, residual-risk presence, patch size.
The judge answers three questions per finding, from masked text only:
  root_cause     is the traced explanation of how the untrusted input reaches the weak spot correct?
  minimal_patch  is the diff the smallest fix, and is it maintainable?
  residual_risk  does the note describe the real remaining risk accurately?
Its answers are printed beside the metrics. They never change a status, a total, a pass or a fail.

The judge must be a different model from the agents and must have an endpoint set in .env (JUDGE_MODEL_NAME,
JUDGE_MODEL_VERSION, JUDGE_ENDPOINT). None is set yet, so the judge does not run and says why. The caller supplies
the model call (`ask`); tests use a stub, which is labelled as a stub.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools._containment import to_model  # noqa: E402
from tools._mask import Masker  # noqa: E402

ANSWERS = ("yes", "no", "unsure")
QUESTIONS = {
    "root_cause": "Is this explanation of how the untrusted input reaches the weak spot correct? Answer yes, no or unsure.",
    "minimal_patch": "Is this diff the smallest change that fixes the weak spot, and is it maintainable? Answer yes, no or unsure.",
    "residual_risk": "Does this residual-risk note describe the real remaining risk accurately? Answer yes, no or unsure.",
}


def judge_config(env_path: str | None = None) -> dict:
    """The judge's model settings from .env (JUDGE_* keys). Missing keys come back as None."""
    values: dict[str, str] = {}
    path = env_path or os.path.join(ROOT, ".env")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                key, sep, value = line.strip().partition("=")
                if sep and not key.startswith("#"):
                    values[key.strip()] = value.strip()
    return {"name": values.get("JUDGE_MODEL_NAME") or None, "version": values.get("JUDGE_MODEL_VERSION") or None,
            "endpoint": values.get("JUDGE_ENDPOINT") or None}


def items_from(findings: list[dict]) -> list[dict]:
    """The text the judge may see, one item per question. No status, no tests, no re-check, no rule id."""
    items = []
    for f in findings:
        base = {"finding_id": f["finding_id"], "quoted_code": f["evidence"]["quoted_code"]}
        cause = f.get("traced_cause")
        if cause:
            items.append({**base, "question": "root_cause", "text": cause["explanation"]})
        if f.get("patch_diff"):
            items.append({**base, "question": "minimal_patch", "text": f["patch_diff"]})
        if f.get("residual_risk"):
            items.append({**base, "question": "residual_risk", "text": f["residual_risk"]})
    return items


def why_not_run(agent_model: dict | None, config: dict) -> str | None:
    """The reason the judge may not run, or None."""
    if not config["name"] or not config["endpoint"]:
        return "no judge model is approved (JUDGE_MODEL_NAME and JUDGE_ENDPOINT are not set in .env)"
    if config["name"] == (agent_model or {}).get("name"):
        return "the judge is the same model as the agents; it must be a different one"
    return None


def summarise(answers: list[dict]) -> dict:
    counts = {q: {a: 0 for a in ANSWERS + ("invalid",)} for q in QUESTIONS}
    for row in answers:
        counts[row["question"]][row["answer"]] += 1
    return counts


def run_judge(items: list[dict], agent_model: dict | None, config: dict, ask=None) -> dict:
    """Ask the judge each item. ``ask(question, masked_text) -> str`` is the model call, supplied by the caller.
    Returns {ran, reason, answers, summary}. Text is masked and checked again before it leaves (to_model)."""
    reason = why_not_run(agent_model, config)
    if reason is None and ask is None:
        reason = "no judge client is connected"
    if reason:
        return {"ran": False, "reason": reason, "answers": [], "summary": None}
    answers = []
    for item in items:
        masker = Masker()
        context = to_model(f"{item['quoted_code']}\n{item['text']}", masker)
        raw = str(ask(QUESTIONS[item["question"]], context)).strip().lower()
        answers.append({"finding_id": item["finding_id"], "question": item["question"],
                        "answer": raw if raw in ANSWERS else "invalid"})
    return {"ran": True, "reason": None, "answers": answers, "summary": summarise(answers)}
