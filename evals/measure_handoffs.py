"""Measure handoffs per scan and SIZE tokens per agent from what actually moves between the parts of the system.

    python evals/measure_handoffs.py [--cases case_01 case_05 ...]

Why this exists: no model is connected (the agents are offline stand-ins), so no run has recorded a real token. The
state counters say 0 in and 0 out. What a run does record is every handoff and every tool call. This script runs each
case and, for each agent, adds up:
  input  = the agent's prompt file (agents/<name>.md) + the job it was given + every tool result it received
  output = the JSON it returned + every tool call (name and arguments) it made
and converts characters to tokens at 4 characters per token. That is a SIZE PROXY, not a measurement: it ignores
re-reads of the context on each model turn, the model's own reasoning and tokenizer differences. Use it to size the
cost model, then replace it with logged tokens from the first real model run (state.counters.tokens).
Handoff counts are exact. Writes out/cost/measured.json.

    python evals/measure_handoffs.py --count-tokens

replaces the proxy with the real Claude tokenizer count for claude-sonnet-5-5 (evals/token_count.py): the same input
and output texts, counted by the token-counting endpoint (no text is generated). It needs AI_MODEL_ENDPOINT set in
.env and ANTHROPIC_API_KEY in the environment, and refuses to start without them. Output tokens are then the tokens of
what the stand-in agents returned, not of what a model would write (reasoning, longer explanations, retries).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agents import offline_agents  # noqa: E402
from agents.mcp_client import McpClient  # noqa: E402
from orchestrator.workflow import Workflow  # noqa: E402

GOLDEN = os.path.join(ROOT, "golden")
RULES = os.path.join(GOLDEN, "rules.json")
CHARS_PER_TOKEN = 4
PROMPT_FILE = {"auditor": "auditor.md", "investigator": "investigator.md", "fixer_validator": "fixer_validator.md"}
AGENTS = ("auditor", "investigator", "fixer_validator")


def tokens(chars: int) -> int:
    return round(chars / CHARS_PER_TOKEN)


def prompt_text(agent: str) -> str:
    with open(os.path.join(ROOT, "agents", PROMPT_FILE[agent]), encoding="utf-8") as handle:
        return handle.read()


def prompt_chars(agent: str) -> int:
    return len(prompt_text(agent))


class Meter:
    """Counts characters moved to and from each agent during one scan."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.inp = defaultdict(int)
        self.out = defaultdict(int)
        self.handoffs = defaultdict(int)
        self.tool_calls = defaultdict(int)
        self.in_text = defaultdict(list)       # what each agent was shown: prompt, job, tool results
        self.out_text = defaultdict(list)      # what each agent produced: tool calls, returned JSON


METER = Meter()
_current = {"agent": None}
_real_call = McpClient.call


def _metered_call(self, name, arguments):
    reply = _real_call(self, name, arguments)
    agent = _current["agent"]
    if agent:
        call_text, reply_text = json.dumps({"name": name, "arguments": arguments}, default=str), json.dumps(reply, default=str)
        METER.out[agent] += len(call_text)
        METER.inp[agent] += len(reply_text)
        METER.out_text[agent].append(call_text)
        METER.in_text[agent].append(reply_text)
        METER.tool_calls[agent] += 1
    return reply


def wrap(agent: str, fn):
    def run(job):
        _current["agent"] = agent
        METER.handoffs[agent] += 1
        job_text = json.dumps(job, default=str)
        METER.inp[agent] += prompt_chars(agent) + len(job_text)
        METER.in_text[agent] += [prompt_text(agent), job_text]
        try:
            out = fn(job)
        finally:
            _current["agent"] = None
        out_text = json.dumps({k: v for k, v in out.items() if k != "usage"}, default=str)
        METER.out[agent] += len(out_text)
        METER.out_text[agent].append(out_text)
        return out
    return run


def measure_case(name: str, work: str, counter=None) -> dict:
    project = os.path.join(work, name)
    shutil.copytree(os.path.join(GOLDEN, name), project, ignore=shutil.ignore_patterns("expected.json"))
    METER.reset()
    agents = {"auditor": wrap("auditor", offline_agents.run_auditor),
              "investigator": wrap("investigator", offline_agents.run_investigator),
              "fixer_validator": wrap("fixer_validator", offline_agents.run_fixer_validator)}
    flow = Workflow(agents=agents, out_root=os.path.join(work, name + "-out"))
    flow.start(project, RULES)           # handoffs happen here; the person's review adds none
    per_agent = {a: {"handoffs": METER.handoffs[a], "tool_calls": METER.tool_calls[a],
                     "in_tokens": tokens(METER.inp[a]), "out_tokens": tokens(METER.out[a])} for a in AGENTS}
    if counter is not None:           # the real tokenizer on the same texts; the proxy stays beside it for comparison
        for a in AGENTS:
            per_agent[a]["proxy_in_tokens"], per_agent[a]["proxy_out_tokens"] = per_agent[a]["in_tokens"], per_agent[a]["out_tokens"]
            per_agent[a]["in_tokens"] = counter.count("\n".join(METER.in_text[a]))
            per_agent[a]["out_tokens"] = counter.count("\n".join(METER.out_text[a]))
    return {"case": name, "steps": flow.state["counters"]["steps"], "per_agent": per_agent,
            "findings": len(flow.state.get("candidate_findings", []))}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--cases", nargs="*")
    parser.add_argument("--count-tokens", action="store_true",
                        help="count real tokens for claude-sonnet-5-5 (needs AI_MODEL_ENDPOINT in .env and ANTHROPIC_API_KEY)")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    counter = None
    if args.count_tokens:
        import token_count
        try:
            counter = token_count.TokenCounter()
        except token_count.CountError as exc:
            print(f"cannot count tokens: {exc}", file=sys.stderr)
            return 2
        print(f"counting tokens with {counter.model} at {counter.approved}")
    McpClient.call = _metered_call
    names = sorted(n for n in os.listdir(GOLDEN) if n.startswith("case_") and int(n[5:7]) <= 11)
    if args.cases:
        names = [n for n in names if any(n.startswith(c) for c in args.cases)]
    work = tempfile.mkdtemp(prefix="saa-measure-")
    rows = []
    try:
        for name in names:
            rows.append(measure_case(name, work, counter))
            print(f"  {name}: {rows[-1]['steps']} handoffs, {rows[-1]['findings']} finding(s)")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    n = len(rows)
    summary = {"scans": n, "handoffs_per_scan": {"mean": sum(r["steps"] for r in rows) / n,
                                                 "min": min(r["steps"] for r in rows), "max": max(r["steps"] for r in rows)},
               "findings_per_scan": sum(r["findings"] for r in rows) / n, "per_agent": {}}
    print(f"\n{n} scans. Handoffs per scan: mean {summary['handoffs_per_scan']['mean']:.1f} "
          f"(min {summary['handoffs_per_scan']['min']}, max {summary['handoffs_per_scan']['max']}); "
          f"findings per scan {summary['findings_per_scan']:.1f}")
    print("Per agent, per scan (" + (f"tokens counted with {counter.model}; output is what the stand-ins returned, not what a model would write)"
                                       if counter else "tokens are a SIZE PROXY at 4 chars per token, not measured)") + ":")
    print(f"  {'agent':<16}{'handoffs':>9}{'tool calls':>11}{'in tokens':>11}{'out tokens':>12}")
    for a in AGENTS:
        stats = {k: sum(r["per_agent"][a][k] for r in rows) / n for k in ("handoffs", "tool_calls", "in_tokens", "out_tokens")}
        summary["per_agent"][a] = stats
        print(f"  {a:<16}{stats['handoffs']:>9.1f}{stats['tool_calls']:>11.1f}{stats['in_tokens']:>11.0f}{stats['out_tokens']:>12.0f}")
    os.makedirs(os.path.join(ROOT, "out", "cost"), exist_ok=True)
    with open(os.path.join(ROOT, "out", "cost", "measured.json"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump({"token_source": (f"counted with {counter.model}" if counter else "proxy: characters / 4, not measured"),
                   "model": counter.model if counter else None, "cases": rows, "summary": summary}, handle, indent=2)
    print("written to out/cost/measured.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
