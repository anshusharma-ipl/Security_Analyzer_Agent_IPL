"""Builds the Guide (ui/site/*.html) that the console serves at /docs. Standard library only.

    python ui/site_build.py

Pages: guide, prompts (how it was built), golden (the 21 test cases), documents (project documents, rendered from markdown).
Inputs: docs_html/data (the parsed playbook, status.md, two captured outputs, case results) and the repository's own .md files.
Re-run docs_html/collect_cases.py first if the code changed and you want fresh case results.
"""
from __future__ import annotations

import json
import os
import re
import sys
from html import escape as e

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "site")
sys.path.insert(0, os.path.join(ROOT, "docs_html"))
sys.path.insert(0, ROOT)

import common  # noqa: E402  (the small markdown renderer)
import build_golden as G  # noqa: E402
import build_prompts as P  # noqa: E402

REPO = "https://github.com/anshusharma-ipl/Security_Analyzer_Agent_IPL"
# The pages, in the order of the tour, in groups. Each page is (key, title, file). The menu numbers them and every page links to the next.
GROUPS = [
    ("The idea", [("summary", "Summary", "summary.html"), ("canvas", "Canvas", "canvas.html"), ("design", "Agent design", "design.html")]),
    ("How it works", [("behaves", "How a scan works", "behaves.html"), ("safe", "Guardrails and safety", "safe.html")]),
    ("The proof", [("testing", "How we test it", "testing.html"), ("results", "Results", "results.html"), ("cost", "Cost", "cost.html")]),
    ("Delivery", [("pilot", "Pilot and kill criteria", "pilot.html"), ("limits", "Limits and next steps", "limits.html"), ("prompts", "How it was built", "prompts.html")]),
]
TOUR = [p for _, pages in GROUPS for p in pages]
TRY = ("run", "Try it yourself", "run.html")
QUESTION = {
    "summary": "What is this, who is it for, and why?",
    "canvas": "What was the original design and business case?",
    "design": "Why an agent, who does what, and which patterns are used?",
    "behaves": "What does a scan do, and what goes in and out?",
    "safe": "What can go wrong, and what stops it?",
    "testing": "How do we score the agents, and on what?",
    "results": "What did the scores say, and what did a real run do?",
    "cost": "What does a scan cost?",
    "pilot": "How does the pilot start, when do we stop, when do we roll back?",
    "limits": "What is not done yet, and what comes next?",
    "prompts": "Which prompts were used to build the agents?",
}
LOGO = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<path d="M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6l8-3z"/><path d="M8.5 12l2.5 2.5L15.5 10"/></svg>')


def page(key: str, title: str, body: str, wide: bool = False, extra_head: str = "", script: str = "") -> str:
    def link(k: str, t: str, h: str, n: int | None = None) -> str:
        cur = ' aria-current="page"' if k == key else ""
        badge = f'<span class="n">{n}</span>' if n else ""
        return f'<a href="/docs/{h}"{cur}>{badge}<span>{t}</span></a>'

    side = f'<a class="scan" href="/"><span class="n">&#9654;</span><span>Scan</span></a>{link(*TRY)}'
    number = 0
    for group, pages in GROUPS:
        side += f'<div class="sgrp">{group}</div>'
        for k, t, h in pages:
            number += 1
            side += link(k, t, h, number)
    pager = ""
    order = [k for k, _, _ in TOUR]
    if key in order:
        i = order.index(key)
        prev = TOUR[i - 1] if i > 0 else None
        nxt = TOUR[i + 1] if i + 1 < len(TOUR) else None
        pager = ('<nav class="pager" aria-label="Previous and next page">'
                 + (f'<a class="prev" href="/docs/{prev[2]}"><small>Previous</small><span>&larr; {prev[1]}</span></a>' if prev else "<span></span>")
                 + (f'<a class="next" href="/docs/{nxt[2]}"><small>Next</small><span>{nxt[1]} &rarr;</span></a>' if nxt else "<span></span>")
                 + "</nav>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)} · Security Analyzer</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Public+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/static/app.css">{extra_head}</head><body>
<header class="topbar"><div class="in"><a class="brand" href="/">{LOGO}Security Analyzer</a></div></header>
<div class="shell"><aside class="side" aria-label="Pages">{side}</aside>
<main class="doc{' wide' if wide else ''}">{body}{pager}</main></div>{script}</body></html>"""


def write(name: str, html: str) -> None:
    path = os.path.join(OUT, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(html)
    print("wrote", os.path.relpath(path, ROOT), f"{len(html) // 1024} KB")


def pill(cls: str, text: str) -> str:
    return f'<span class="pill {cls}">{e(text)}</span>'


# --------------------------------------------------------------------------- markdown with real headings
def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", re.sub(r"[`*]", "", text).lower()).strip("-")[:48]


HEADINGS: list = []


def md_with_quotes(text: str) -> str:
    """common.md, plus '> ' lines rendered as a block quote."""
    parts, run, quote = [], [], False
    for line in text.split("\n") + [None]:
        is_q = line is not None and line.startswith(">")
        if line is not None and is_q == quote:
            run.append(line[1:].lstrip() if is_q else line)
            continue
        if run:
            body = "\n".join(run)
            parts.append(f"<blockquote>{common.md(body)}</blockquote>" if quote else common.md(body))
        run, quote = ([line[1:].lstrip() if is_q else line] if line is not None else []), is_q
    return "".join(parts)


def render_md(text: str) -> str:
    HEADINGS.clear()
    chunks, buf, fence = [], [], False
    for line in text.split("\n"):
        if line.startswith("```"):
            fence = not fence
        m = None if fence else re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            if buf:
                chunks.append(("md", "\n".join(buf)))
                buf = []
            chunks.append(("h", (len(m.group(1)), m.group(2))))
        else:
            buf.append(line)
    if buf:
        chunks.append(("md", "\n".join(buf)))
    out = []
    for kind, val in chunks:
        if kind == "h":
            HEADINGS.append((val[0], val[1], slug(val[1])))
            out.append(f'<h{val[0]} id="{slug(val[1])}">{common._inline(val[1])}</h{val[0]}>')
        else:
            out.append(md_with_quotes(val))
    html = "".join(out)
    html = re.sub(r'<pre([^>]*)>', r'<pre\1>', html)
    return html


ARCH = """<svg viewBox="0 0 920 520" role="img" aria-label="Architecture sketch. Inputs and a person feed a workflow orchestrator, which hands work to three agents one at a time. The Auditor reads the source files, the Fixer and Validator writes only in a temporary copy, and all three agents use the AI model service. The orchestrator writes the report, patch file and audit log.">
<style>.t{font:600 14px var(--sans);fill:var(--ink)}.s{font:12.5px var(--sans);fill:var(--ink-2)}.m{font:12px var(--mono);fill:var(--ink-2)}
.b{fill:var(--surface);stroke:var(--line);stroke-width:1.5}.o{fill:var(--info-bg);stroke:var(--brand);stroke-width:1.5}.d{fill:var(--sunk);stroke:var(--line);stroke-width:1.5}.a{stroke:var(--ink-3);stroke-width:1.5;fill:none;marker-end:url(#ah)}.a2{stroke:var(--ink-3);stroke-width:1.5;fill:none;marker-end:url(#ah);marker-start:url(#ah)}</style>
<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="var(--ink-3)"/></marker></defs>
<rect class="b" x="20" y="10" width="250" height="62" rx="9"/><text class="t" x="36" y="36">Inputs</text><text class="s" x="36" y="56">Code folder, tests, rules.json</text>
<rect class="b" x="650" y="10" width="250" height="62" rx="9"/><text class="t" x="666" y="36">Person</text><text class="s" x="666" y="56">Approves, edits or rejects each fix</text>
<path class="a" d="M145 72 L290 128"/><path class="a2" d="M775 72 L630 128"/>
<rect class="o" x="210" y="128" width="500" height="76" rx="10"/><text class="t" x="228" y="156">Workflow orchestrator (not an agent)</text><text class="s" x="228" y="178">Order, limits, approvals, decision log, report</text>
<rect class="b" x="750" y="128" width="150" height="76" rx="9"/><text class="t" x="764" y="156">Output</text><text class="s" x="764" y="176">Report, patch file,</text><text class="s" x="764" y="192">audit log</text>
<path class="a" d="M710 166 L750 166"/>
<path class="a" d="M290 204 L155 258"/><path class="a" d="M460 204 L460 258"/><path class="a" d="M630 204 L765 258"/>
<rect class="b" x="20" y="258" width="270" height="104" rx="9"/><text class="t" x="36" y="284">1. Auditor</text><text class="s" x="36" y="304">Finds and ranks findings</text><text class="m" x="36" y="330">list_files, read_file,</text><text class="m" x="36" y="346">run_security_rules</text>
<rect class="b" x="325" y="258" width="270" height="104" rx="9"/><text class="t" x="341" y="284">2. Investigator</text><text class="s" x="341" y="304">Traces the cause, picks a fix approach</text><text class="m" x="341" y="330">read_file,</text><text class="m" x="341" y="346">read_code_structure</text>
<rect class="b" x="630" y="258" width="270" height="104" rx="9"/><text class="t" x="646" y="284">3. Fixer and Validator</text><text class="s" x="646" y="304">Fixes, tests, keeps / retries / rejects</text><text class="m" x="646" y="330">apply_patch, run_tests,</text><text class="m" x="646" y="346">request_recheck</text>
<path class="a" d="M155 362 L155 420"/><path class="a" d="M765 362 L765 420"/>
<path class="a" d="M200 362 L370 420"/><path class="a" d="M460 362 L460 420"/><path class="a" d="M720 362 L550 420"/>
<rect class="d" x="20" y="420" width="270" height="80" rx="9"/><text class="t" x="36" y="446">Source files</text><text class="s" x="36" y="466">Read only</text>
<rect class="o" x="325" y="420" width="270" height="80" rx="9"/><text class="t" x="341" y="446">AI model service</text><text class="s" x="341" y="466">Sees code with sensitive</text><text class="s" x="341" y="482">values hidden</text>
<rect class="d" x="630" y="420" width="270" height="80" rx="9"/><text class="t" x="646" y="446">Temporary copy</text><text class="s" x="646" y="466">The only place anything is written</text>
</svg>"""


# --------------------------------------------------------------------------- the diagram
DIAGRAM = """<svg viewBox="0 0 920 334" role="img" aria-label="A person reviews fixes. A plain-code orchestrator hands work to three agents one at a time. Each agent has its own tools. Originals are read only; the temporary copy is the only place anything is written.">
<style>.t{font:600 14px var(--sans);fill:var(--ink)}.s{font:12.5px var(--sans);fill:var(--ink-2)}.m{font:12px var(--mono);fill:var(--ink-2)}
.b{fill:var(--surface);stroke:var(--line);stroke-width:1.5}.o{fill:var(--info-bg);stroke:var(--brand);stroke-width:1.5}.a{stroke:var(--ink-3);stroke-width:1.5;fill:none;marker-end:url(#h)}</style>
<defs><marker id="h" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="var(--ink-3)"/></marker></defs>
<rect class="b" x="10" y="20" width="130" height="70" rx="10"/><text class="t" x="75" y="52" text-anchor="middle">You</text><text class="s" x="75" y="72" text-anchor="middle">approve, edit, reject</text>
<rect class="o" x="190" y="20" width="720" height="70" rx="10"/><text class="t" x="206" y="46">Workflow orchestrator: plain code, not an agent</text>
<text class="s" x="206" y="68">Order, limits, handoff log, approvals, report. Agents never call each other.</text>
<path class="a" d="M140 55 H188"/><path class="a" d="M188 62 H142" />
<g><rect class="b" x="190" y="140" width="220" height="86" rx="10"/><text class="t" x="204" y="166">Auditor</text><text class="s" x="204" y="186">Scans the whole project.</text><text class="s" x="204" y="204">Keeps findings that have proof.</text></g>
<g><rect class="b" x="450" y="140" width="220" height="86" rx="10"/><text class="t" x="464" y="166">Investigator</text><text class="s" x="464" y="186">Traces the cause of one finding.</text><text class="s" x="464" y="204">Or hands it to a person.</text></g>
<g><rect class="b" x="710" y="140" width="200" height="86" rx="10"/><text class="t" x="724" y="166">Fixer and Validator</text><text class="s" x="724" y="186">Writes a patch, runs the tests.</text><text class="s" x="724" y="204">Re-checks the rules.</text></g>
<path class="a" d="M300 90 V138"/><path class="a" d="M560 90 V138"/><path class="a" d="M810 90 V138"/>
<text class="m" x="190" y="244">list_files, read_file,</text><text class="m" x="190" y="258">run_security_rules</text><text class="m" x="450" y="244">read_file,</text><text class="m" x="450" y="258">read_code_structure</text><text class="m" x="710" y="244">apply_patch, run_tests,</text><text class="m" x="710" y="258">request_recheck</text>
<rect class="b" x="190" y="276" width="330" height="46" rx="8"/><text class="t" x="204" y="296">Your folder: read only</text><text class="s" x="204" y="313">Fingerprinted before and after the scan.</text>
<rect class="b" x="560" y="276" width="350" height="46" rx="8"/><text class="t" x="574" y="296">Temporary copy: the only place anything is written</text><text class="s" x="574" y="313">Patches and test runs happen here, then it is deleted.</text>
</svg>"""


# --------------------------------------------------------------------------- guide


# --------------------------------------------------------------------------- the tour: pages built from docs/PRD.md and the guide text
# --------------------------------------------------------------------------- the tour: pages built from docs/PRD.md and written text
def prd_sections() -> dict:
    """docs/PRD.md split on its numbered '## N. Title' headings: {N: (title, markdown body)}."""
    with open(os.path.join(ROOT, "docs", "PRD.md"), encoding="utf-8") as handle:
        text = handle.read().replace("\r\n", "\n")
    out = {}
    for part in re.split(r"(?m)^## ", text)[1:]:
        title, _, body = part.partition("\n")
        m = re.match(r"(\d+)\.\s+(.*)", title)
        if m:
            out[int(m.group(1))] = (m.group(2).strip(), body.strip("\n"))
    return out


def prd_split(n: int) -> tuple:
    """(text before the first '###', {sub-heading: its markdown including the heading line}), numbers stripped from the sub-headings."""
    body = re.sub(r"(?m)^(###) \d+\.\d+\s+", r"\1 ", prd_sections()[n][1])
    parts = re.split(r"(?m)^(?=### )", body)
    pre = parts[0] if parts and not parts[0].startswith("### ") else ""
    subs = {}
    for part in parts:
        if part.startswith("### "):
            subs[part.split("\n", 1)[0][4:].strip()] = part
    return pre, subs


def prd_html(n: int, skip: tuple = ()) -> str:
    pre, subs = prd_split(n)
    keep = [pre] + [text for title, text in subs.items() if title not in skip]
    return f'<div class="md">{render_md(chr(10).join(keep))}</div>'


def prd_sub(n: int, title: str) -> str:
    """One sub-section of a PRD section, without its heading line."""
    text = prd_split(n)[1][title]
    return f'<div class="md">{render_md(text.split(chr(10), 1)[1])}</div>'


def lead(title: str, lede: str) -> str:
    return f'<h1>{e(title)}</h1><p class="lede">{lede}</p>'


def related(*slugs: tuple) -> str:
    links = " · ".join(f'<a href="/docs/md/{s}.html">{e(t)}</a>' for s, t in slugs)
    return f'<p class="small muted">Source documents: {links}</p>'


def strip_head(html_text: str) -> str:
    """A page body without its first <h1> and lede, for reuse as a section of another page."""
    return re.sub(r'^\s*<h1>.*?</h1>\s*<p class="lede">.*?</p>', "", html_text, count=1, flags=re.S)


def demote(html_text: str) -> str:
    """Headings one level down, for a page body that becomes a section of another page."""
    return html_text.replace("<h2>", "<h3>").replace("</h2>", "</h3>")


def live_data() -> dict | None:
    src = os.path.join(ROOT, "docs_html", "data", "live_run.json")
    if not os.path.isfile(src):
        return None
    with open(src, encoding="utf-8") as handle:
        return json.load(handle)


def case_scores() -> tuple:
    n_pass = n_gold = n_held = n_red = 0
    for c in G.CASES:
        _, label, _ = G.verdict(c)
        ok = label == "Matches" or label.startswith("Red-team: HELD")
        if int(c["id"].split("_")[1]) >= 12:
            n_red += 1
            n_held += ok
        else:
            n_gold += 1
            n_pass += ok
    return n_pass, n_gold, n_held, n_red


def build_summary() -> str:
    n_pass, n_gold, n_held, n_red = case_scores()
    live = live_data()
    tiles = f'<div class="tile"><b>{n_pass} of {n_gold}</b><span>golden cases pass</span></div><div class="tile"><b>{n_held} of {n_red}</b><span>red-team attacks held ({n_red - n_held} weaknesses found)</span></div>'
    if live:
        cost = live["tokens"]["input"] * 2 / 1e6 + live["tokens"]["output"] * 8 / 1e6
        tiles += (f'<div class="tile"><b>{live["totals"]["fixed_and_verified"]} of {live["totals"]["found"]}</b><span>findings fixed in a live {e(live["model"].upper())} run</span></div>'
                  f'<div class="tile"><b>about ${cost:.2f}</b><span>per scan of the demo project</span></div>')
    criteria = [
        ("Problem and user", "summary", "Who has the problem, and why a scanner alone does not solve it"),
        ("Why agentic, and the design", "design", "What the agents decide, the tools each has, and the patterns used"),
        ("Orchestration and tool use", "behaves", "How a scan runs, step by step, with limits and hand-over"),
        ("Guardrails and human oversight", "safe", "Failure modes, guardrails, and a person approving every fix"),
        ("Evaluation", "testing", "The golden set, the red team and how each result is judged"),
        ("Results and evidence", "results", "The quality scorecard and one real run with a model"),
        ("Cost and feasibility", "cost", "What a scan costs and what it would cost at volume"),
        ("Rollout and risk", "pilot", "The pilot plan, kill criteria and rollback"),
        ("Honest limits", "limits", "What is not done, and what comes next"),
        ("How it was built", "prompts", "The prompts used with Claude Code to build it"),
    ]
    pages = {k: (t, h) for k, t, h in TOUR}
    crit = "".join(f'<tr><td>{c}</td><td><a href="/docs/{pages[k][1]}">{pages[k][0]}</a></td><td>{d}</td></tr>' for c, k, d in criteria)
    tour = "".join(f'<tr><td>{i + 1}</td><td><a href="/docs/{h}">{t}</a></td><td>{QUESTION[k]}</td></tr>' for i, (k, t, h) in enumerate(TOUR))
    body = lead("Summary", "It scans a Python project for weak spots, proposes a fix for each, tests the fix in a temporary copy, then waits for you to approve, edit or reject it. It never changes your files.") + f"""
<div class="cards">
<div class="card"><h3>Finds</h3><p>SQL injection, command injection and path traversal. It also reports hard-coded secrets, weak password hashes and unpinned packages, but never fixes those.</p></div>
<div class="card"><h3>Proposes and tests</h3><p>Each fix is applied to a temporary copy, the project's own tests run, and the rules run again. A fix counts as verified only if both pass.</p></div>
<div class="card"><h3>Asks you</h3><p>Every fix waits for a person. Approved fixes are written to <code>fixes.patch</code>. You apply them yourself.</p></div>
</div>
<h2>Proof at a glance</h2>
<div class="tiles">{tiles}</div>
<p class="small muted">Golden cases are realistic projects with a known answer. The red team is a set of attacks written to break the system, so finding weaknesses is its job. The live run is one real scan, not a benchmark. Details are on the <a href="/docs/results.html">Results</a> page.</p>
<h2>The problem and the idea</h2>
{prd_html(1, skip=("Why an agent and not a script",))}
<h2>The job and what success looks like</h2>
{prd_html(2)}
<h2>Where to find each capstone criterion</h2>
<div class="tw"><table><tr><th>Criterion</th><th>Page</th><th>What you will find</th></tr>{crit}</table></div>
<h2>How to read this site</h2>
<p>The pages follow one story, in order. Use the menu on the left, or the Next link at the bottom of each page. The source is in the <a href="{REPO}">repository</a>.</p>
<div class="tw"><table><tr><th>#</th><th>Page</th><th>The question it answers</th></tr>{tour}</table></div>
"""
    return page("summary", "Summary", body)


def build_design() -> str:
    cards = "".join(f'<a class="card" href="/docs/md/{k}.html"><h3>{e(v["title"])}</h3><p>{e(short(v["plain"], 120))}</p></a>' for k, v in P.AGENT_TEXT.items() if k in ("auditor", "investigator", "fixer_validator"))
    body = lead("Agent design", "The design decisions behind the agent team: why an agent, who does what, how they are connected, and which agentic patterns are used.") + f"""
<h2>1. Why an agent and not a script</h2>
{prd_sub(1, "Why an agent and not a script")}
<h2>2. The team</h2>
<p>Three agents, each with one job and its own tools, and a plain-code orchestrator that is not a model.</p>
{prd_sub(3, "Roles and tools")}
<h2>3. The architecture</h2>
<div class="figure">{ARCH}</div>
<p>Every handoff goes through the orchestrator. The agents never call each other, and the original files are read only.</p>
<h2>4. Agentic patterns used</h2>
<div class="tw"><table><tr><th>Pattern</th><th>Used</th><th>How</th></tr>
<tr><td>Multi-agent with an orchestrator</td><td>{pill("ok", "Yes")}</td><td>Three agents with separate jobs, coordinated by plain code.</td></tr>
<tr><td>Pipeline</td><td>{pill("ok", "Yes")}</td><td>A scan is seven fixed steps, in a fixed order.</td></tr>
<tr><td>Tool use with least privilege</td><td>{pill("ok", "Yes")}</td><td>Seven tools. Each agent gets only its own, through its own MCP profile.</td></tr>
<tr><td>Routing and hand-over</td><td>{pill("ok", "Yes")}</td><td>Each finding is routed: fix, retry, or hand to a person.</td></tr>
<tr><td>Reflection and retry</td><td>{pill("ok", "Yes")}</td><td>The rules run again on the fixed copy, and a failed fix gets one retry.</td></tr>
<tr><td>Human in the loop</td><td>{pill("ok", "Yes")}</td><td>A person approves, edits or rejects every fix.</td></tr>
<tr><td>Parallel agents</td><td>{pill("", "No")}</td><td>One handoff at a time, so every step is logged in order.</td></tr>
<tr><td>Free-form planning</td><td>{pill("", "No")}</td><td>The order is fixed by the orchestrator, not chosen by a model.</td></tr>
<tr><td>Retraining the model</td><td>{pill("", "No")}</td><td>The model is not retrained. Failed and rejected fixes are added to the test set instead.</td></tr></table></div>
<h2>5. State and contracts</h2>
<div class="tw"><table><tr><th>Part</th><th>How it works</th></tr>
<tr><td>Shared state</td><td>One document owned by the orchestrator. Each field has one writer, so an agent cannot overwrite what it does not own.</td></tr>
<tr><td>Contracts</td><td>Every agent reply is checked against a JSON schema before the orchestrator accepts it.</td></tr>
<tr><td>Decisions</td><td>The orchestrator, not an agent, sets the final status. "Verified" comes from test and re-check results.</td></tr></table></div>
<h2>6. What each agent is told</h2>
<p>The text each agent is given at run time is kept in the repository and shown here.</p>
<div class="cards">{cards}</div>
{related(("roster", "Roster: single or several agents"), ("AGENTS", "AGENTS.md: the team spec"))}
"""
    return page("design", "Agent design", body)


def build_behaves() -> str:
    body = lead("How a scan works", "How a scan runs, what goes in and what comes out, which limits apply, and when it hands a finding to a person.") + f"""
<h2>A scan, step by step</h2>
<div class="figure">{DIAGRAM}</div>
<p>A scan is seven fixed steps, run by the orchestrator (plain code, not an agent):</p>
<ol>
<li>Check the rules file.</li>
<li>Fingerprint your files and make a temporary copy.</li>
<li>The Auditor scans the whole project and ranks the findings.</li>
<li>For each finding, the Investigator traces the cause, and the Fixer and Validator writes and tests a patch.</li>
<li>You decide on each fix.</li>
<li>The orchestrator checks that your original files are unchanged.</li>
<li>It writes the log and the report.</li></ol>
<h2>The details</h2>
{prd_html(3, skip=("Roles and tools",))}
{related(("AGENTS", "AGENTS.md: scope, limits and decisions"), ("DEMO", "Demo script"))}
"""
    return page("behaves", "How a scan works", body)


def build_safe() -> str:
    return page("safe", "Guardrails and safety", lead("Guardrails and safety", "What can go wrong, and the guardrails that stop it.") + prd_html(4) + related(("AGENTS", "AGENTS.md: the never list")))


def red_counts() -> tuple:
    rows = P.REDTEAM_ROWS
    return sum(1 for r in rows if r[2] != "BROKE"), sum(1 for r in rows if r[2] == "BROKE")


def build_testing() -> str:
    body = lead("How we test it", "We score the agents against small projects with known right answers, and repeat it whenever something changes.") + f"""
{prd_html(6)}
<h2>The test cases</h2>
{demote(strip_head(build_golden(inner=True)))}
{related(("RUN_SUMMARY", "Results of every check run"))}
"""
    return page("testing", "How we test it", body)


def build_results() -> str:
    held, broke = red_counts()
    live = demote(strip_head(build_live(inner=True))) if live_data() else ""
    body = lead("Results", "Where the agents stand against the quality bar, and what one real run with a model did.") + f"""
<h2>Quality standards</h2>
{prd_html(5)}
<h3>In short</h3>
<div class="tw"><table><tr><th>Status</th><th>What</th></tr>
<tr><td>{pill("ok", "Works")}</td><td>A scan runs end to end, the safety gates hold (no write to your files, evidence on every finding, all eight kill switches pass), and one live GPT-5 run fixed 7 of 10 findings for about $0.75 in about 19 minutes.</td></tr>
<tr><td>{pill("risk", "Not yet")}</td><td>The false-fix rate is 27% against a limit of 5%, and {broke} of 10 red-team attacks still break the system ({held} are stopped).</td></tr></table></div>
<h3>Why we track these</h3>
<p>The first two are non-negotiable: without evidence a person cannot review a finding, and a write to your files breaks the promise the tool makes. The others show whether the fixes can be trusted. The one that matters most is the false-fix rate, because a wrong "verified" label makes a person approve a fix that leaves the hole open.</p>
<h2>The live GPT-5 run</h2>
{live}
{related(("RUN_SUMMARY", "Results of every check run"))}
"""
    return page("results", "Results", body)


def build_pilot() -> str:
    body = lead("Pilot and kill criteria", "How the pilot starts, when we stop at once, and when we go back to the previous setup.") + f"""
<h2>Rollout</h2>
{prd_html(8)}
<h2>Kill criteria and rollback</h2>
{prd_html(9)}
{related(("PILOT", "Pilot plan: setup, time comparison and rollback table"))}
"""
    return page("pilot", "Pilot and kill criteria", body)


def build_limits() -> str:
    held, broke = red_counts()
    body = lead("Limits and next steps", "What is not done yet, stated plainly, and what we would do next.") + f"""
<h2>What is not done yet</h2>
<div class="tw"><table><tr><th>Area</th><th>Where it stands</th></tr>
<tr><td>Red team</td><td>{broke} of 10 attacks still break the system. None of the weaknesses is fixed yet.</td></tr>
<tr><td>False-fix rate</td><td>27% with the built-in agents against a limit of 5%. Not measured on the live run, because nobody independently checked the approved fixes.</td></tr>
<tr><td>Model coverage</td><td>One full scan with GPT-5. Claude has run through a local bridge. The Gemini adapter has only been tested against a mock server.</td></tr>
<tr><td>Sample size</td><td>About one test case per type and one live run, so the scores are a direction, not a proof.</td></tr>
<tr><td>Time saved</td><td>Not measured. Reviewer time per fix, and the manual comparison, need real reviewers.</td></tr>
<tr><td>Cost baseline</td><td>The price rates need checking against a real price card, and today's engineer hours per finding are not measured.</td></tr>
<tr><td>Judge model</td><td>Built and tested with a stub. No judge model is set up, so there is no live result.</td></tr>
<tr><td>Tracing service</td><td>A tracing integration sends model requests to a third-party service. It must be approved, or switched off, before any pilot.</td></tr>
<tr><td>Pilot setup</td><td>Participants, the repository and the rules owner are still to be named.</td></tr></table></div>
<h2>Next steps, in order</h2>
<div class="tw"><table><tr><th>#</th><th>Step</th><th>Why it comes now</th></tr>
<tr><td>1</td><td>Fix the four most serious red-team failures (secrets reaching run files, patches that edit tests, false fixes, missing usage counts) and re-run.</td><td>They break guardrails a pilot depends on.</td></tr>
<tr><td>2</td><td>Score a model-backed run on all 21 cases.</td><td>It shows whether a model closes the gaps of the built-in agents.</td></tr>
<tr><td>3</td><td>Have a person label every approved fix as right or wrong.</td><td>It gives a real false-fix rate on a live run.</td></tr>
<tr><td>4</td><td>Record reviewer time and compare it with manual work on the same examples.</td><td>It is the only way to claim time saved.</td></tr>
<tr><td>5</td><td>Set up the judge model and compare it with a person on at least 20 findings.</td><td>It adds a check on explanation and patch quality.</td></tr>
<tr><td>6</td><td>Confirm the price card, and approve the model provider and the tracing service.</td><td>They fix the cost figure and the data-handling policy.</td></tr>
<tr><td>7</td><td>Name the pilot participants, repository and rules owner, then start.</td><td>The pilot cannot begin without them.</td></tr></table></div>
{related(("PILOT", "Pilot plan"), ("RUN_SUMMARY", "Results of every check run"))}
"""
    return page("limits", "Limits and next steps", body)


def build_run() -> str:
    body = lead("Try it yourself", "Start the console, give it a project, and read the result.") + """
<h2>How to run it</h2>
<p>You need Python 3.11 or newer and one package: <code>pip install jsonschema</code>. A live scan needs the console running on your own machine or a server. The published site on GitHub Pages is read-only: it cannot scan or call a model.</p>
<ol>
<li><b>Start the console.</b> Run <code>python ui/server.py</code> and open <code>http://127.0.0.1:8765</code>.</li>
<li><b>Give it your code.</b> Drop your project folder or a .zip on the left (it should include its tests), or choose <b>Use the demo project</b> (13 findings across six rule types, plus safe files that must produce nothing).</li>
<li><b>Connect a model (optional).</b> Choose a provider, paste your key, press <b>Connect</b>, then <b>Test</b>. Without one, the built-in agents run, need no key and send nothing anywhere.</li>
<li><b>Press Run scan.</b> Watch each agent work. For every ready fix press <b>Approve this fix</b> or reject it, enter your name and press <b>Finish</b>.</li>
<li><b>Take the result.</b> The report, the decision log and <code>fixes.patch</code> are on the run's page. Nothing is applied to your files; you apply <code>fixes.patch</code>.</li></ol>

<h2 id="model">Connect a model</h2>
<ol>
<li>In the console's <b>Model</b> panel choose OpenAI (GPT), Anthropic (Claude) or Google (Gemini), pick or type a model name and paste your API key. The request format follows from the provider. Or put <code>AI_MODEL_ENDPOINT</code>, <code>AI_MODEL_NAME</code> and a key (<code>OPENAI_API_KEY</code>, <code>ANTHROPIC_API_KEY</code> or <code>GEMINI_API_KEY</code>) in a <code>.env</code> file and press <b>Use .env</b>.</li>
<li>Press <b>Test</b>. It sends one tiny message with no project data.</li>
<li>By default all three agents use the model. You can leave any of them on the built-in version.</li>
<li>Run a scan. The header shows the AI calls and tokens used.</li></ol>
<p>Secrets and personal data are masked before anything is sent. The model never receives a path, rules file or test command that the harness did not give it. Use fake or non-sensitive code until your security team has approved the provider.</p>
""" + related(("README", "README"), ("DEMO", "Demo script"), ("DEPLOY", "Hosting notes"), ("UX_REVIEW", "UX review of the console"))
    return page("run", "Try it yourself", body)


# --------------------------------------------------------------------------- prompts
PHASES = [("Foundations", ["0", "1", "2"]), ("Contracts and tools", ["3", "4A", "4B", "4C"]), ("Agents and workflow", ["5"]),
          ("Guardrails", ["6A", "6B"]), ("Measurement", ["7A", "7B", "8", "9"]), ("Pilot gate", ["10"])]


def short(text: str, n: int = 190) -> str:
    text = text.strip()
    cut = text.split(". ")[0].rstrip(".") + "."
    return cut if len(cut) <= n else text[: n].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def prompt_item(sid: str, s: dict) -> str:
    n = P.NOTES[sid]
    title = re.sub(r"^(Step \d+|Prompt \d[A-C]) · ", "", s["heading"])
    prompt = "\n".join(l for l in s["prompt"] if not l.startswith("Using an existing repo instead"))
    return (f'<details class="item" id="step-{sid}"><summary><span class="num">{sid}</span><div class="sum"><b>{e(title)}</b><span>{e(short(n["plain"]))}</span></div></summary>'
            f'<div class="body"><h4>The prompt</h4><pre>{e(prompt)}</pre></div></details>')


def build_prompts() -> str:
    by_id = {}
    for s in P.steps:
        if s["prompt"]:
            by_id[P.step_id(s["heading"])] = s
    states = []
    parts = []
    for name, ids in PHASES:
        parts.append(f'<div class="phase">{e(name)}</div>' + "".join(prompt_item(i, by_id[i]) for i in ids))
    body = f"""<h1>How it was built</h1>
<p class="lede">These are the fifteen prompts used with Claude Code to build the agents, in the order they were run. Open one to read it.</p>
<p class="small muted">Each prompt produced code, tests and a commit. How well the result scores is on the <a href="/docs/results.html">Results</a> page, and the agents' instructions are on the <a href="/docs/design.html">Agent design</a> page.</p>
{"".join(parts)}
{related(("status", "The coding agent's own status report"))}
"""
    return page("prompts", "How it was built", body)


# --------------------------------------------------------------------------- golden dataset
def build_golden(inner: bool = False) -> str:
    gold, red = [], []
    n_pass = n_held = 0
    for c in G.CASES:
        cls, label, why = G.verdict(c)
        passed = label == "Matches" or label.startswith("Red-team: HELD")
        num = c["id"].split("_")[1]
        is_red = int(num) >= 12
        short = c["id"][:7]
        idx = c.get("index") or {"category": re.sub(r"^Red team: ", "Red team: ", c["expected"].get("category", "Red team")),
                                 "input": G.RED_PLAIN.get(short, ""),
                                 "expected_output": c["expected"].get("expected_fix") or c["expected"].get("reason") or "See the answer key in the repository.",
                                 "why_in_set": "Added in the red-team step to attack the system, not to show a normal run."}
        files = "".join(f'<details><summary><code>{e(f["path"])}</code></summary><pre>{e(f["text"])}</pre></details>' for f in c["files"])
        word = ("Held" if passed else "Broke it") if is_red else ("Pass" if passed else "Fail")
        row = (f'<details class="item"><summary><span class="num">{num}</span><div class="sum"><b>{e(idx["category"])}</b><span>{e(idx["input"])}</span></div>{pill("ok" if passed else "risk", word)}</summary><div class="body">'
               f'<h4>Expected</h4><p>{e(idx["expected_output"])}</p><h4>What happened</h4><p>{e(why)}</p><h4>Why it is in the set</h4><p>{e(idx["why_in_set"])}</p>'
               f'<h4>Code</h4>{files}<p class="small faint mono">{e(c["id"])}</p></div></details>')
        if is_red:
            red.append(row)
            n_held += passed
        else:
            gold.append(row)
            n_pass += passed
    n_gold, n_red = len(gold), len(red)
    attacks = "".join(
        f'<tr><td>{a}</td><td>{e(b)}</td><td>{pill("risk" if c == "BROKE" else "ok", "Broke it" if c == "BROKE" else "Held")}</td><td>{e(d)}</td></tr>'
        for a, b, c, d in P.REDTEAM_ROWS)
    body = f"""<h1>The 21 test cases</h1>
<p class="lede">The test cases are small projects with a known right answer. After each run we compare what the agents did with that answer. They come in two sets with two different purposes, scored separately.</p>
<div class="tw"><table><tr><th>Set</th><th>Cases</th><th>Purpose</th><th>Result</th></tr>
<tr><td><b>Golden cases</b></td><td>1 to 11</td><td>Realistic projects, one per type the canvas asks for. They show whether the agents do the job.</td><td><b>{n_pass} of {n_gold} pass</b></td></tr>
<tr><td><b>Red-team cases</b></td><td>12 to 21</td><td>Hostile inputs written on purpose to break the system. They find weaknesses before an attacker or a pilot does.</td><td><b>{n_held} of {n_red} held</b>, {n_red - n_held} weaknesses found</td></tr></table></div>

<h2>Golden cases (1 to 11)</h2>
<p>Each one is graded against its answer key. <b>Pass</b> means the system found the expected problem and ended in the expected state: a fix ready for approval, handed to a person, or nothing reported for safe code. <b>Fail</b> means it did something else. Open a case to see what happened. The failures come from the built-in agents, which only handle some fix shapes; a model-backed agent is meant to close them.</p>
{"".join(gold)}

<h2>Red-team cases (12 to 21)</h2>
<p>These are attacks, so finding weaknesses is their job. <b>Held</b> means the system stopped the attack. <b>Broke it</b> means the attack got through a guardrail. Each weakness is recorded with the smallest fix we propose, and none is fixed yet. Run them with <code>python evals/redteam.py</code>.</p>
<div class="tw"><table><tr><th>Case</th><th>Attack</th><th>Result</th><th>What went wrong</th></tr>{attacks}</table></div>
{"".join(red)}
<p class="small muted">The score summary for all runs is in the <a href="/docs/md/RUN_SUMMARY.html">results document</a>.</p>
"""
    return body if inner else page("golden", "Test cases", body)


# --------------------------------------------------------------------------- the live run
def build_live(inner: bool = False) -> str:
    """The Live run page, from docs_html/data/live_run.json (written by docs_html/collect_live_run.py)."""
    src = os.path.join(ROOT, "docs_html", "data", "live_run.json")
    if not os.path.isfile(src):
        return ""
    with open(src, encoding="utf-8") as handle:
        run = json.load(handle)
    t = run["totals"]
    mins = round(run["elapsed_seconds"] / 60)

    def outcome(f: dict) -> tuple:
        if f["status"] == "verified_awaiting_approval":
            ok = (f.get("approval") or {}).get("decision") == "approved"
            return ("ok", "Fixed and approved" if ok else "Fix ready")
        return ("wait", "Left to a person")

    def why(f: dict) -> str:
        if f["status"] == "verified_awaiting_approval":
            return ""
        if f.get("reason") == "fix not allowed":
            return "This rule is report-only: a code change cannot fix it, so it is shown as a task for a person."
        return f.get("reason") or ""

    rows, details = [], []
    for f in run["findings"]:
        att = f["attempts"]
        tries = f"{len(att)}" if att else "none"
        tests = (f["tests"] or {}).get("after") or "not run"
        rows.append(f'<tr><td>{e(f["id"])}</td><td>{e(f["rule"])}</td><td><code>{e(f["file"])}:{f["line"]}</code></td><td>{pill(*outcome(f))}</td><td>{tries}</td><td>{e(tests)}</td><td>{e((f.get("recheck") or "not run").replace("_", " "))}</td></tr>')
        parts = [f'<h4>Evidence</h4><pre>{e(f["quoted_code"] or "")}</pre>']
        tc = f.get("traced_cause") or {}
        if tc.get("explanation"):
            parts.append(f'<h4>Traced cause</h4><p>{e(tc["explanation"])}</p>')
        if f.get("patch_diff"):
            parts.append(f'<h4>The fix</h4><pre>{e(f["patch_diff"])}</pre>')
        if att:
            parts.append('<h4>Attempts</h4><div class="tw"><table><tr><th>Attempt</th><th>Tests after</th><th>Re-check</th><th>Decision</th></tr>' + "".join(
                f'<tr><td>{a["attempt"]}</td><td>{e(a["tests_after"] or "")}</td><td>{e(a["recheck"] or "")}</td><td>{e(a["decision"] or "")}</td></tr>' for a in att) + "</table></div>")
        if f.get("residual_risk"):
            parts.append(f'<h4>Residual risk</h4><p>{e(f["residual_risk"])}</p>')
        if why(f):
            parts.append(f'<h4>Why a person must decide</h4><p>{e(why(f))}</p>')
        ap = f.get("approval")
        if ap:
            parts.append(f'<h4>Decision</h4><p>{e(ap["decision"].capitalize())} by {e(ap["reviewer"])} at {e(ap["timestamp"])}.</p>')
        details.append(f'<details class="item"><summary><span class="num">{e(f["id"])}</span><div class="sum"><b>{e(f["rule"])} in <code>{e(f["file"])}</code></b><span>Line {f["line"]}, severity {e(f["severity"])}</span></div>{pill(*outcome(f))}</summary><div class="body">{"".join(parts)}</div></details>')

    by_agent: dict = {}
    for h in run["handoffs"]:
        by_agent[h["agent"]] = by_agent.get(h["agent"], 0) + 1
    names = {"auditor": "Auditor", "investigator": "Investigator", "fixer_validator": "Fixer and Validator"}
    agent_rows = "".join(f"<tr><td>{names.get(a, a)}</td><td>{n}</td></tr>" for a, n in by_agent.items())
    trace = "".join(f'<tr><td>{h["step"]}</td><td>{names.get(h["agent"], h["agent"])}</td><td>{e(h["job"])}</td><td>{e(h["finding_id"] or "")}</td><td>{e(h["result"])}</td></tr>' for h in run["handoffs"])
    reviewers = sorted({(f.get("approval") or {}).get("reviewer", "") for f in run["findings"] if f.get("approval")})

    body = f"""<h1>The live run</h1>
<p class="lede">What a real scan did when the three agents ran on {e(run["model"].upper())} against the demo project. Everything here is taken from that run's own report files. It is one run, not a benchmark.</p>

<div class="tiles">
<div class="tile"><b>{t["found"]}</b><span>findings</span></div>
<div class="tile"><b>{t["fixed_and_verified"]}</b><span>fixed and approved</span></div>
<div class="tile"><b>{t["needs_a_person"]}</b><span>left to a person</span></div>
<div class="tile"><b>{run["ai_calls"]}</b><span>AI calls, about {mins} minutes</span></div>
</div>
<p class="small muted">Run <code>{e(run["run_id"])}</code> on {e(run["date"])}. {run["tokens"]["input"]:,} input and {run["tokens"]["output"]:,} output tokens. What this costs is on the <a href="/docs/cost.html">Cost</a> page.</p>

<h2>1. What it found and did</h2>
<p>Each row is one finding. "Attempts" counts fix attempts: the Fixer may try once more if its first fix fails the tests. "Tests" and "Re-check" are the results after the final fix.</p>
<div class="tw"><table><tr><th>Finding</th><th>Rule</th><th>Where</th><th>Outcome</th><th>Attempts</th><th>Tests</th><th>Re-check</th></tr>{"".join(rows)}</table></div>

<h2>2. The detail of each finding</h2>
<p>Open one to see the evidence, the traced cause, the fix as a diff, and who decided.</p>
{"".join(details)}

<h2>3. What the agents did</h2>
<p>The orchestrator handed work to the agents {len(run["handoffs"])} times. Agents never call each other, so this list is the whole run.</p>
<div class="tw"><table><tr><th>Agent</th><th>Handoffs</th></tr>{agent_rows}</table></div>
<details class="item"><summary><div class="sum"><b>The full step-by-step trace</b><span>{len(run["handoffs"])} handoffs</span></div></summary><div class="body"><div class="tw"><table><tr><th>Step</th><th>Agent</th><th>Job</th><th>Finding</th><th>Result</th></tr>{trace}</table></div></div></details>

<h2>4. Safety checks in this run</h2>
<div class="tw"><table><tr><th>Check</th><th>Result</th></tr>
<tr><td>Original files unchanged</td><td>{"Yes" if run["originals_unchanged"] else "No"}</td></tr>
<tr><td>Tests passed before any change</td><td>{e(run["baseline_tests"] or "")}</td></tr>
<tr><td>A run limit was hit</td><td>{"No" if not run["cap_hit"] else e(str(run["cap_hit"]))}</td></tr>
<tr><td>Every fix decided by a person</td><td>Yes: {e(", ".join(reviewers))}. Nothing was applied automatically.</td></tr>
<tr><td>Sensitive values masked before the model saw them</td><td>{run["sensitive_items_hidden"]} found in this project</td></tr></table></div>
"""
    return body if inner else page("live", "Live run", body)


# --------------------------------------------------------------------------- documents
DOCS = [
    ("Start here", [("README", "README.md", "What the project is and how to run it"), ("DEMO", "DEMO.md", "A four-run demo script with exact commands"), ("DEPLOY", "docs/DEPLOY.md", "How to host the console, and the risks")]),
    ("Decisions", [("AGENTS", "AGENTS.md", "The team spec: scope, roster, tools, limits"), ("roster", "docs/roster.md", "Single agent or several, and why the Auditor stays"), ("canvas", "canvas.md", "The original canvas: agents, tools, guardrails, quality bar, kill criteria"), ("cost", "docs/cost.md", "What a scan costs, measured on a live run")]),
    ("Pilot", [("PILOT", "docs/PILOT.md", "Pilot setup, kill criteria, rollback and scale-up")]),
    ("Agent instructions", [("auditor", "agents/auditor.md", "What the Auditor is told"), ("investigator", "agents/investigator.md", "What the Investigator is told"), ("fixer_validator", "agents/fixer_validator.md", "What the Fixer and Validator is told")]),
    ("Review", [("RUN_SUMMARY", "docs/RUN_SUMMARY.md", "Results of every check run: tests, test cases, red team, kill switches, live model runs"), ("UX_REVIEW", "docs/UX_REVIEW.md", "UX review of the console and what changed"), ("status", "docs_html/data/status.md", "The coding agent's own build status report")]),
]


def build_canvas() -> str:
    with open(os.path.join(ROOT, "canvas.md"), encoding="utf-8") as handle:
        text = handle.read()
    text = re.sub(r"```mermaid.*?```", "ARCHDIAGRAMHERE", text, flags=re.S)
    html = render_md(re.sub(r"^\*(?!\*)(.+?)(?<!\*)\*$", r"\1", text, flags=re.M))
    html = html.replace("<p>ARCHDIAGRAMHERE</p>", '<div class="figure">' + ARCH + '</div>').replace("ARCHDIAGRAMHERE", '<div class="figure">' + ARCH + '</div>')
    note = ('<p class="small muted">This is the Agent Opportunity Canvas the project was built from (<code>canvas.md</code>). It is the source for the agent roles, tools, guardrails, quality bar and kill criteria. '
            'If it and another document disagree, the canvas and <a href="/docs/md/AGENTS.html">AGENTS.md</a> win until the team changes them.</p>')
    html = html.replace("</h1>", "</h1>" + note, 1)
    toc = []
    for level, title, sid in HEADINGS:
        if level in (1, 4):
            continue
        toc.append(f'<a class="{"part" if level == 2 else ""}" href="#{sid}">{e(re.sub(r"[`*]", "", title))}</a>')
    body = f"""<div class="canvas"><nav class="ctoc" aria-label="Canvas sections"><b>The original canvas</b>{"".join(toc)}</nav>
<article class="md">{html}</article></div>"""
    return page("canvas", "Canvas", body, wide=True)


COST_PAGE = r"""<h1>What a scan costs</h1>
<p class="lede">One real scan, measured: the agents ran on GPT-5 against the demo project (10 findings in 28 files). Every number on this page comes from that run or is simple arithmetic on it.</p>

<h2>At a glance</h2>
<div class="tiles">
<div class="tile"><b>$0.75</b><span>cost of one scan</span></div>
<div class="tile"><b>236,478</b><span>tokens (190,198 in, 46,280 out)</span></div>
<div class="tile"><b>81</b><span>AI calls, about 19 minutes</span></div>
<div class="tile"><b>7 of 10</b><span>findings fixed; 3 left to a person</span></div>
</div>
<p class="small muted">Run <code>run-001</code> on 2026-10-29, project <code>shop_demo</code>, model GPT-5. The scan finished inside its limits: 81 of 150 calls, 28 of 50 steps, 1,143 of 2,400 seconds. Finding F007 (command injection) needed one retry because the first fix called an <code>echo</code> program that does not exist on Windows; the second attempt removed the subprocess call.</p>

<h2>1. What it costs, by token type</h2>
<div class="tw"><table><tr><th>Token type</th><th>Tokens</th><th>Rate per 1M tokens</th><th>Cost</th></tr>
<tr><td>Input (what the model reads)</td><td>190,198</td><td>$2.00</td><td>$0.38</td></tr>
<tr><td>Output (what the model writes, including reasoning)</td><td>46,280</td><td>$8.00</td><td>$0.37</td></tr>
<tr><td><b>Total</b></td><td><b>236,478</b></td><td></td><td><b>$0.75</b></td></tr></table></div>
<p class="small muted">The rates are the ones used for this report. Check them against your own price card before planning a budget. With prompt caching on input (if it applies), the total would fall to about $0.56.</p>

<h2>2. What it costs at your volume</h2>
<p>The same scan, repeated. Assumes 22 working days a month and the cost of this run for every scan (the run already includes the model re-reading its context and retrying, so no extra multiplier is added).</p>
<div class="tw"><table><tr><th>Scans per day</th><th>Scans per month</th><th>Tokens per month</th><th>Cost per month</th></tr>
<tr><td>5</td><td>110</td><td>26 million</td><td>about $83</td></tr>
<tr><td>20</td><td>440</td><td>104 million</td><td>about $330</td></tr>
<tr><td>100</td><td>2,200</td><td>520 million</td><td>about $1,650</td></tr></table></div>
<p class="small muted">A larger project, or one with more findings, costs more: on this run each finding used about 23,600 tokens.</p>

<h2>3. Cost per finding</h2>
<div class="tw"><table><tr><th>Finding</th><th>File</th><th>Rule</th><th>Outcome</th><th>Estimated cost</th></tr>
<tr><td>F001</td><td>src/customers.py</td><td>SQL injection</td><td>Fixed and approved</td><td>$0.075</td></tr>
<tr><td>F002</td><td>src/lookup.py</td><td>SQL injection</td><td>Fixed and approved</td><td>$0.075</td></tr>
<tr><td>F003</td><td>src/products.py</td><td>SQL injection</td><td>Fixed and approved</td><td>$0.075</td></tr>
<tr><td>F004</td><td>src/reports.py</td><td>SQL injection</td><td>Needs a person (redesign)</td><td>$0.038</td></tr>
<tr><td>F005</td><td>src/service.py</td><td>SQL injection</td><td>Fixed and approved</td><td>$0.075</td></tr>
<tr><td>F006</td><td>src/users.py</td><td>SQL injection</td><td>Fixed and approved</td><td>$0.075</td></tr>
<tr><td>F007</td><td>src/netcheck.py</td><td>Command injection</td><td>Fixed on retry and approved</td><td>$0.113</td></tr>
<tr><td>F008</td><td>src/files.py</td><td>Path traversal</td><td>Fixed and approved</td><td>$0.075</td></tr>
<tr><td>F009</td><td>src/config.py</td><td>Secret</td><td>Needs a person (never auto-fixed)</td><td>$0.019</td></tr>
<tr><td>F010</td><td>requirements.txt</td><td>Dependency pin</td><td>Needs a person (never auto-fixed)</td><td>$0.019</td></tr>
<tr><td><b>Total</b></td><td></td><td></td><td></td><td><b>$0.75</b></td></tr></table></div>
<p class="small muted">The per-finding figures are shares of the total, estimated from how much work each finding needed, not separate meter readings.</p>

<h2>4. Cost per agent</h2>
<div class="tw"><table><tr><th>Agent</th><th>What it did</th><th>Steps</th><th>Estimated tokens</th><th>Estimated cost</th></tr>
<tr><td>Auditor</td><td>1 scan and 8 re-checks</td><td>9</td><td>about 75,700</td><td>$0.24</td></tr>
<tr><td>Investigator</td><td>10 investigations</td><td>10</td><td>about 85,100</td><td>$0.27</td></tr>
<tr><td>Fixer and Validator</td><td>1 baseline test run and 8 fix attempts</td><td>9</td><td>about 75,700</td><td>$0.24</td></tr>
<tr><td><b>Total</b></td><td></td><td><b>28</b></td><td><b>236,478</b></td><td><b>$0.75</b></td></tr></table></div>
<p class="small muted">The three agents cost about the same. The split is an estimate; the run recorded only the total.</p>

<h2>5. The same tokens on other models</h2>
<p>What 236,478 tokens would cost at other list prices. This is only a price comparison: a different model would use a different number of tokens and give different fixes, so it has to be measured before it is chosen.</p>
<div class="tw"><table><tr><th>Model</th><th>Provider</th><th>Input per 1M</th><th>Output per 1M</th><th>Total</th><th>Compared with GPT-5</th></tr>
<tr><td><b>GPT-5 (used)</b></td><td>OpenAI</td><td>$2.00</td><td>$8.00</td><td>$0.75</td><td></td></tr>
<tr><td>GPT-5-mini</td><td>OpenAI</td><td>$0.40</td><td>$1.60</td><td>$0.15</td><td>5 times cheaper</td></tr>
<tr><td>claude-sonnet-5-5</td><td>Anthropic</td><td>$3.00</td><td>$15.00</td><td>$1.26</td><td>1.7 times more</td></tr>
<tr><td>claude-haiku-5-5</td><td>Anthropic</td><td>$0.80</td><td>$4.00</td><td>$0.34</td><td>2.2 times cheaper</td></tr>
<tr><td>gemini-flash-latest</td><td>Google</td><td>$0.15</td><td>$0.60</td><td>$0.056</td><td>13 times cheaper</td></tr>
<tr><td>gemini-pro-latest</td><td>Google</td><td>$1.25</td><td>$5.00</td><td>$0.47</td><td>1.6 times cheaper</td></tr></table></div>

<h2>6. Efficiency</h2>
<div class="tw"><table><tr><th>Measure</th><th>Value</th></tr>
<tr><td>Cost per verified fix</td><td>$0.107 ($0.75 for 7 fixes)</td></tr>
<tr><td>Cost per AI call</td><td>$0.009 (81 calls)</td></tr>
<tr><td>Cost per file scanned</td><td>$0.027 (28 files)</td></tr>
<tr><td>Tokens per finding</td><td>23,648 (10 findings)</td></tr>
<tr><td>Output tokens against the cap</td><td>77% used (46,280 of 60,000)</td></tr>
<tr><td>Time against the cap</td><td>48% used (1,143 of 2,400 seconds)</td></tr></table></div>
"""


def build_cost() -> str:
    return page("cost", "Cost at production volume", COST_PAGE)


def doc_body(text: str) -> str:
    """A document page: an 'On this page' row of section links (when there are several sections) above the rendered text."""
    html = render_md(text)
    tops = [(t, sid) for lvl, t, sid in HEADINGS if lvl == 2]
    toc = ""
    if len(tops) >= 4:
        toc = '<p class="small faint" style="margin:0 0 6px">On this page</p><div class="toc docnav">' + "".join(f'<a href="#{sid}">{e(re.sub(r"[`*]", "", t))}</a>' for t, sid in tops) + "</div>"
    return f'{toc}<div class="md">{html}</div>'


def build_documents() -> None:
    """Render the repository's other markdown documents to md/*.html. The tour pages link to them where they matter."""
    for slug_, path, blurb in (item for _, items in DOCS for item in items):
        full = os.path.join(ROOT, path)
        if slug_ == "canvas" or not os.path.isfile(full):
            continue
        with open(full, encoding="utf-8") as handle:
            text = handle.read()
        title = re.sub(r"[`*]", "", (re.search(r"^#\s+(.*)", text, re.M) or [None, slug_])[1])
        write(f"md/{slug_}.html", page("documents", title, f'<p class="small"><a href="/docs/summary.html">Summary</a> · <span class="faint">{e(path)}</span></p>{doc_body(text)}', wide=True))


def main() -> int:
    for name in ("guide.html", "measure.html", "quality.html", "live.html", "golden.html", "rollout.html", "kill.html", "documents.html", os.path.join("md", "PRD.html")):
        old = os.path.join(OUT, name)                                    # pages that no longer exist
        if os.path.isfile(old):
            os.remove(old)
    write("summary.html", build_summary())
    write("design.html", build_design())
    write("behaves.html", build_behaves())
    write("safe.html", build_safe())
    write("testing.html", build_testing())
    write("results.html", build_results())
    write("pilot.html", build_pilot())
    write("limits.html", build_limits())
    write("run.html", build_run())
    write("prompts.html", build_prompts())
    write("canvas.html", build_canvas())
    write("cost.html", build_cost())
    build_documents()  # md/*.html: roster, results, pilot plan, deploy notes and the rest
    return 0


if __name__ == "__main__":
    sys.exit(main())
