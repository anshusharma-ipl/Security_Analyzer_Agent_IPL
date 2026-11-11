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
NAV = [("guide", "Guide", "guide.html"), ("prd", "PRD", "md/PRD.html"), ("cost", "Cost", "cost.html"), ("canvas", "Canvas", "canvas.html"), ("prompts", "How it was built", "prompts.html"), ("golden", "Test cases", "golden.html")]
LOGO = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<path d="M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6l8-3z"/><path d="M8.5 12l2.5 2.5L15.5 10"/></svg>')


def page(key: str, title: str, body: str, wide: bool = False, extra_head: str = "", script: str = "") -> str:
    nav = '<a href="/">Scan</a>' + "".join(f'<a href="/docs/{h}"{" aria-current=page" if k == key else ""}>{t}</a>' for k, t, h in NAV)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)} · Security Analyzer</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Public+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/static/app.css">{extra_head}</head><body>
<header class="topbar"><div class="in"><a class="brand" href="/">{LOGO}Security Analyzer</a><nav class="nav" aria-label="Main">{nav}</nav></div></header>
<main class="doc{' wide' if wide else ''}">{body}</main>{script}</body></html>"""


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


def build_guide() -> str:
    red = P.read(P.D, "captured", "s8_redteam.txt")
    m = re.search(r"Summary: (\d+) held, (\d+) broke the system, of (\d+)", red)
    held, broke = (m.group(1), m.group(2)) if m else ("?", "?")
    body = f"""
<h1>How the Security Analyzer works</h1>
<p class="lede">It scans a Python project for weak spots, proposes a fix for each, tests the fix in a temporary copy, then waits for you to approve, edit or reject it. It never changes your files.</p>
<div class="toc"><a href="#pages">What each page is for</a><a href="#does">What it does</a><a href="#works">How it works</a><a href="#run">How to run it</a><a href="#model">Connect a model</a><a href="#stands">Where it stands</a></div>

<h2 id="pages">What each page is for</h2>
<p>Each page answers one question. You do not need all of them: pick the one that matches what you want to know.</p>
<div class="tw"><table><tr><th>Page</th><th>Question it answers</th></tr>
<tr><td><a href="/docs/guide.html">Guide</a> (this page)</td><td>What is this, how do I run it, and does it work?</td></tr>
<tr><td><a href="/docs/md/PRD.html">PRD</a></td><td>What are we building, for whom, how safe is it, and when do we stop?</td></tr>
<tr><td><a href="/docs/cost.html">Cost</a></td><td>What does a scan cost, and what would it cost at our volume?</td></tr>
<tr><td><a href="/docs/canvas.html">Canvas</a></td><td>What was the original design and business case?</td></tr>
<tr><td><a href="/docs/prompts.html">How it was built</a></td><td>Which prompts were used to build the agents?</td></tr>
<tr><td><a href="/docs/golden.html">Test cases</a></td><td>How do we know the agents do the right thing?</td></tr></table></div>

<h2 id="does">What it does</h2>
<div class="cards">
<div class="card"><h3>Finds</h3><p>SQL injection, command injection and path traversal. It also reports hard-coded secrets, weak password hashes and unpinned packages, but never fixes those.</p></div>
<div class="card"><h3>Proposes and tests</h3><p>Each fix is applied to a temporary copy, the project's own tests run, and the rules run again. A fix counts as verified only if both pass.</p></div>
<div class="card"><h3>Asks you</h3><p>Every fix waits for a person. Approved fixes are written to <code>fixes.patch</code>. You apply them yourself.</p></div>
</div>

<h2 id="works">How it works</h2>
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
<p>Three rules hold the design together:</p>
<ul>
<li>Each agent can use only its own tools.</li>
<li>A fix is called verified by the orchestrator from test results, never by an agent's opinion.</li>
<li>Anything the agent is unsure about goes to a person.</li></ul>
<p>More: the <a href="/docs/canvas.html">canvas</a> is the original design, and the <a href="/docs/md/roster.html">roster</a> explains why there are three agents and one plain-code orchestrator.</p>

<h2 id="run">How to run it</h2>
<p>You need Python 3.11 or newer and one package: <code>pip install jsonschema</code>. A live scan needs the console running on your own machine or a server. The published site on GitHub Pages is read-only: it cannot scan or call a model.</p>
<ol>
<li><b>Start the console.</b> Run <code>python ui/server.py</code> and open <code>http://127.0.0.1:8765</code>.</li>
<li><b>Give it your code.</b> Drop your project folder or a .zip on the left (it should include its tests), or choose <b>Use the demo project</b> (13 findings across six rule types, plus safe files that must produce nothing).</li>
<li><b>Connect a model (optional).</b> Choose a provider, paste your key, press <b>Connect</b>, then <b>Test</b>. Without one, the built-in agents run, need no key and send nothing anywhere.</li>
<li><b>Press Run scan.</b> Watch each agent work. For every ready fix press <b>Approve this fix</b> or reject it, enter your name and press <b>Finish</b>.</li>
<li><b>Take the result.</b> The report, the decision log and <code>fixes.patch</code> are on the run's page. Nothing is applied to your files; you apply <code>fixes.patch</code>.</li></ol>
<p>If you leave the page while a scan runs, come back to the console and it reconnects to the scan.</p>
<pre class="code" style="padding:12px 16px"><code>python ui/server.py                                   # the console
python -m orchestrator.cli run &lt;folder&gt; golden/rules.json   # the same scan from a terminal
python -m unittest discover -s tests                  # the tests
python evals/run_evals.py                             # score the 21 test cases
python kill_checks.py --run                           # the eight kill switches</code></pre>
<p><b>Safety.</b> To check a fix, the project's own tests run on the machine that hosts the console. Host it only where that is acceptable, scan only code you trust, and put it behind a token if anyone else can reach it. <a href="/docs/md/DEPLOY.html">Hosting notes</a>.</p>

<h2 id="model">Connect a model</h2>
<ol>
<li>In the console's <b>Model</b> panel choose OpenAI (GPT), Anthropic (Claude) or Google (Gemini), pick or type a model name and paste your API key. The request format follows from the provider. Or put <code>AI_MODEL_ENDPOINT</code>, <code>AI_MODEL_NAME</code> and a key (<code>OPENAI_API_KEY</code>, <code>ANTHROPIC_API_KEY</code> or <code>GEMINI_API_KEY</code>) in a <code>.env</code> file and press <b>Use .env</b>.</li>
<li>Press <b>Test</b>. It sends one tiny message with no project data.</li>
<li>By default all three agents use the model. You can leave any of them on the built-in version.</li>
<li>Run a scan. The header shows the AI calls and tokens used.</li></ol>
<p>Secrets and personal data are masked before anything is sent. The model never receives a path, rules file or test command that the harness did not give it. Use fake or non-sensitive code until your security team has approved the provider.</p>

<h2 id="stands">Where it stands</h2>
<p>We measure the agents in two ways. Read the table with these two columns in mind:</p>
<ul>
<li><b>Offline agents</b> are the built-in agents with no model, scored on the 21 <a href="/docs/golden.html">test cases</a>. It is about one case per type, so treat these numbers as a direction.</li>
<li><b>Live GPT-5 run</b> is one real scan of the demo project on 2026-10-29 (10 findings, 28 files). It is one run, not an average.</li></ul>
<div class="tw"><table><tr><th>Measure</th><th>What it tells you</th><th>Target</th><th>Offline agents</th><th>Live GPT-5</th><th>Status</th></tr>
<tr><td>Evidence on every finding</td><td>Each finding shows file, line and the code, so a person can check it</td><td>100%</td><td>100%</td><td></td><td>{pill("ok", "Met")}</td></tr>
<tr><td>Writes to originals or outside the copy</td><td>The safety boundary held</td><td>0</td><td>0</td><td>0</td><td>{pill("ok", "Met")}</td></tr>
<tr><td>High-severity recall</td><td>Serious weak spots are not missed</td><td>90% or more</td><td>100%</td><td></td><td>{pill("ok", "Met")}</td></tr>
<tr><td>Finding precision</td><td>Few false alarms</td><td>85% or more</td><td>89%</td><td></td><td>{pill("ok", "Met")}</td></tr>
<tr><td>Verified-fix success</td><td>Share of fixable findings that end with a tested fix</td><td>75% or more</td><td>80%</td><td>70% (7 of 10)</td><td>{pill("wait", "Close on the live run")}</td></tr>
<tr><td>False-fix rate</td><td>How often "verified" is wrong</td><td>5% or less</td><td>27%</td><td>not measured</td><td>{pill("risk", "Not met")}</td></tr>
<tr><td>Tests pass for verified fixes</td><td>A fix never breaks the project's tests</td><td>100%</td><td>100%</td><td>100%</td><td>{pill("ok", "Met")}</td></tr>
<tr><td>Audit record complete</td><td>Every decision is logged</td><td>100%</td><td>100%</td><td>100%</td><td>{pill("ok", "Met")}</td></tr>
<tr><td>Reviewer approval rate</td><td>People accept the fixes that are offered</td><td>70% or more</td><td></td><td>100% (7 of 7)</td><td>{pill("ok", "Met on one run")}</td></tr></table></div>
<p><b>Why we track these.</b> The first two are non-negotiable: without evidence a person cannot review a finding, and a write to your files breaks the promise the tool makes. The others show whether the fixes can be trusted. The one that matters most is the false-fix rate, because a wrong "verified" label makes a person approve a fix that leaves the hole open.</p>

<h3>Other results</h3>
<ul>
<li><b>The live run:</b> 10 findings, 7 fixed and approved, 3 left to a person (a redesign, a secret and a dependency, which are never auto-fixed). One command-injection fix needed a retry. Your originals were unchanged. It used 81 AI calls and 236,478 tokens, about $0.75, in about 19 minutes. No limit was hit and no kill switch fired. See the <a href="/docs/cost.html">cost page</a>.</li>
<li><b>Red team:</b> {held} of 10 attacks were stopped and {broke} broke the system. None of the {broke} is fixed yet. They are listed on the <a href="/docs/golden.html">test cases page</a>.</li>
<li><b>Kill switches:</b> all eight checks pass.</li>
<li><b>Tests:</b> all 173 pass.</li>
<li><b>Models:</b> GPT-5 has run live to completion. Claude has run through a local bridge. The Gemini adapter has only been tested against a mock server.</li></ul>

<p>More: <a href="/docs/md/PRD.html">PRD</a> · <a href="/docs/md/RUN_SUMMARY.html">Results of the offline runs</a> · <a href="/docs/md/DEPLOY.html">Deploy</a> · <a href="/docs/md/UX_REVIEW.html">UX review</a> · <a href="{REPO}">Repository</a></p>
"""
    return page("guide", "Guide", body)


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
<p class="small muted">Each prompt produced code, tests and a commit. How well the result scores is on the <a href="/docs/golden.html">Test cases</a> and <a href="/docs/cost.html">Cost</a> pages.</p>
{"".join(parts)}
<h2>The three agents' instructions</h2>
<p>The text each agent is given at run time is separate from the prompts above.</p>
<div class="cards">{"".join(f'<a class="card" href="/docs/md/{k}.html"><h3>{e(v["title"])}</h3><p>{e(short(v["plain"], 120))}</p></a>' for k, v in P.AGENT_TEXT.items() if k in ("auditor", "investigator", "fixer_validator"))}</div>
"""
    return page("prompts", "How it was built", body)


# --------------------------------------------------------------------------- golden dataset
def build_golden() -> str:
    cls_map = {"ok": "ok", "bad": "risk", "warn": "wait"}
    rows, counts = [], {"match": 0, "mismatch": 0, "red": 0}
    for c in G.CASES:
        cls, label, why = G.verdict(c)
        grp = "match" if label == "Matches" else "red" if label.startswith(("Red-team", "Needs")) else "mismatch"
        counts[grp] += 1
        short = c["id"][:7]
        idx = c.get("index") or {"category": re.sub(r"^Red team: ", "Red team: ", c["expected"].get("category", "Red team")),
                                 "input": G.RED_PLAIN.get(short, ""),
                                 "expected_output": c["expected"].get("expected_fix") or c["expected"].get("reason") or "See the answer key in the repository.",
                                 "why_in_set": "Added in the red-team step to attack the system, not to show a normal run."}
        files = "".join(f'<details><summary><code>{e(f["path"])}</code></summary><pre>{e(f["text"])}</pre></details>' for f in c["files"])
        num = c["id"].split("_")[1]
        rows.append(f'<details class="item" data-g="{grp}"><summary><span class="num">{num}</span><div class="sum"><b>{e(idx["category"])}</b><span>{e(idx["input"])}</span></div>{pill(cls_map.get(cls, "info"), "Differs" if label == "Mismatch" else label)}</summary><div class="body">'
                    f'<h4>Expected</h4><p>{e(idx["expected_output"])}</p><h4>What happened</h4><p>{e(why)}</p><h4>Why it is in the set</h4><p>{e(idx["why_in_set"])}</p>'
                    f'<h4>Code</h4>{files}<p class="small faint mono">{e(c["id"])}</p></div></details>')
    attacks = "".join(
        f'<tr><td>{a}</td><td>{e(b)}</td><td>{pill("risk" if c == "BROKE" else "ok", "Broke it" if c == "BROKE" else "Held")}</td><td>{e(d)}</td></tr>'
        for a, b, c, d in P.REDTEAM_ROWS)
    body = f"""<h1>The 21 test cases</h1>
<p class="lede">The test cases are small projects with a known right answer. After each run we compare what the agents did with that answer. This is how we know whether the system works.</p>
<div class="statline"><div><b>{counts['match']}</b><span>match the answer key</span></div><div><b>{counts['mismatch']}</b><span>differ from it</span></div><div><b>{counts['red']}</b><span>are red-team cases</span></div></div>

<h2>What the labels mean</h2>
<div class="tw"><table><tr><th>Label</th><th>What it means</th><th>What to do with it</th></tr>
<tr><td>{pill("ok", "Matches")}</td><td>The agents reported the expected finding and ended in the expected state (a fix ready for approval, or handed to a person, or nothing reported for safe code).</td><td>Nothing. This is the goal.</td></tr>
<tr><td>{pill("risk", "Differs")}</td><td>The run did not match the answer key: a finding was missed, reported on the wrong line, or ended in a different state, for example handed to a person where a fix was expected.</td><td>Open the case. "What happened" says exactly where it differs. Most differences come from the built-in agents, which patch only some kinds of fixes; a model-backed Fixer is meant to close them.</td></tr>
<tr><td>{pill("ok", "Red-team: Held")}</td><td>A hostile input was tried and the system stopped it.</td><td>Nothing.</td></tr>
<tr><td>{pill("risk", "Red-team: Broke it")}</td><td>A hostile input got past a guardrail. These cases are written to find weak spots, so some are expected to break the system today.</td><td>Each is listed below with the smallest fix we propose.</td></tr></table></div>
<p class="small muted">Cases 1 to 11 are the types the canvas asks for. Cases 12 to 21 are hostile inputs added for the red team. The score summary for all runs is in the <a href="/docs/md/RUN_SUMMARY.html">results document</a>.</p>

<h2>All 21 cases</h2>
<div class="chips" role="group" aria-label="Filter"><button class="on" data-f="all">All</button><button data-f="match">Matches</button><button data-f="mismatch">Differs</button><button data-f="red">Red team</button></div>
{"".join(rows)}

<h2>The ten red-team attacks</h2>
<p>Run with <code>python evals/redteam.py</code>. {sum(1 for r in P.REDTEAM_ROWS if r[2] != "BROKE")} held and {sum(1 for r in P.REDTEAM_ROWS if r[2] == "BROKE")} broke the system. None of the failures is fixed yet.</p>
<div class="tw"><table><tr><th>Case</th><th>Attack</th><th>Result</th><th>What went wrong</th></tr>{attacks}</table></div>
"""
    script = """<script>document.querySelectorAll('.chips button').forEach(b=>b.onclick=()=>{document.querySelectorAll('.chips button').forEach(x=>x.classList.toggle('on',x===b));
document.querySelectorAll('.item[data-g]').forEach(d=>d.hidden=b.dataset.f!=='all'&&d.dataset.g!==b.dataset.f)})</script>"""
    return page("golden", "Test cases", body, script=script)


# --------------------------------------------------------------------------- documents
DOCS = [
    ("Start here", [("PRD", "docs/PRD.md", "The AI-native PRD: contract, quality bar, failure modes, eval plan, cost"), ("README", "README.md", "What the project is and how to run it"), ("DEMO", "DEMO.md", "A four-run demo script with exact commands"), ("DEPLOY", "docs/DEPLOY.md", "How to host the console, and the risks")]),
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


def build_documents() -> str:
    parts = []
    for group, items in DOCS:
        cards = []
        for slug_, path, blurb in items:
            slug_name = slug_
            full = os.path.join(ROOT, path)
            if not os.path.isfile(full):
                continue
            if slug_ == "canvas":
                cards.append(f'<a class="card" href="/docs/canvas.html"><h3>Canvas</h3><p>{e(blurb)}</p></a>')
                continue
            with open(full, encoding="utf-8") as handle:
                text = handle.read()
            title = (re.search(r"^#\s+(.*)", text, re.M) or [None, slug_])[1]
            title = re.sub(r"[`*]", "", title)
            write(f"md/{slug_}.html", page("prd" if slug_ == "PRD" else "documents", title, f'<p class="small"><a href="/docs/guide.html">Guide</a> · <span class="faint">{e(path)}</span></p>{doc_body(text)}', wide=True))
            cards.append(f'<a class="card" href="/docs/md/{slug_}.html"><h3>{e(re.sub(chr(96), "", title) if len(title) < 46 else slug_)}</h3><p>{e(blurb)}</p></a>')
        if cards:
            parts.append(f'<h2>{e(group)}</h2><div class="cards">{"".join(cards)}</div>')
    body = f"""<h1>Project documents</h1><p class="lede">Everything written for the project, in one place. The repository is at <a href="{REPO}">{REPO.split("github.com/")[1]}</a>.</p>
<div class="cards"><a class="card" href="/docs/guide.html"><h3>Guide</h3><p>How it works, was built and runs</p></a><a class="card" href="/docs/prompts.html"><h3>How it was built</h3><p>Each prompt and what came out</p></a><a class="card" href="/docs/canvas.html"><h3>Canvas</h3><p>The original agent design</p></a><a class="card" href="/docs/golden.html"><h3>Test cases</h3><p>The 21 golden cases</p></a></div>{"".join(parts)}"""
    return page("documents", "Documents", body)


def main() -> int:
    write("guide.html", build_guide())
    write("prompts.html", build_prompts())
    write("golden.html", build_golden())
    write("canvas.html", build_canvas())
    write("cost.html", build_cost())
    build_documents()  # writes md/*.html (PRD, run summary, ...); there is no index page
    return 0


if __name__ == "__main__":
    sys.exit(main())
