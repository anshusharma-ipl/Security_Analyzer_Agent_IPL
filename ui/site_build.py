"""Builds the Guide (ui/site/*.html) that the console serves at /docs. Standard library only.

    python ui/site_build.py

Pages: guide, prompts (how it was built), golden (the 21 test cases), documents (project documents, rendered from markdown).
Inputs: docs_html/data (the parsed playbook, two captured outputs, case results) and the repository's own .md files.
Re-run docs_html/collect_cases.py first if the code changed and you want fresh case results.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
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
    ("The idea", [("summary", "Problem and idea", "summary.html"), ("design", "Agent design", "design.html"), ("prompts", "How we built", "prompts.html"), ("testing", "Evals and testing", "testing.html")]),
    ("How it runs", [("behaves", "How a scan works", "behaves.html"), ("safe", "Guardrails", "safe.html"), ("kill", "Kill criteria and rollback", "kill.html"), ("cost", "Cost", "cost.html")]),
    ("Results and plan", [("results", "Results", "results.html"), ("pilot", "Pilot plan", "pilot.html"), ("limits", "Limits and next steps", "limits.html")]),
]
TOUR = [p for _, pages in GROUPS for p in pages]
TRY = ("run", "Try it yourself", "run.html")
QUESTION = {
    "summary": "What is the problem, and what is the idea?",
    "design": "Why an agent, who does what, and which patterns are used?",
    "behaves": "What does a scan do, and what goes in and out?",
    "safe": "What can go wrong, and what stops it?",
    "kill": "When does a run stop at once, and when do we go back to the previous setup?",
    "testing": "How is each agent evaluated, and on what?",
    "results": "What did the scores say, and what did a real run do?",
    "cost": "What does a scan cost?",
    "pilot": "How does the pilot start and who takes part?",
    "limits": "What is not done yet, and what comes next?",
    "prompts": "How was it built, and with which prompts?",
}
LOGO = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<path d="M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6l8-3z"/><path d="M8.5 12l2.5 2.5L15.5 10"/></svg>')


def side_html(key: str) -> str:
    """The left menu: Scan, Try it yourself, then the numbered tour in groups. `key` marks the current page ("scan" for the console)."""
    def link(k: str, t: str, h: str, n: int | None = None) -> str:
        cur = ' aria-current="page"' if k == key else ""
        badge = f'<span class="n">{n}</span>' if n else ""
        return f'<a href="/docs/{h}"{cur}>{badge}<span>{t}</span></a>'

    scan_cur = ' aria-current="page"' if key == "scan" else ""
    side = f'<a class="scan" href="/"{scan_cur}><span class="n">&#9654;</span><span>Scan</span></a>{link(*TRY)}'
    number = 0
    for group, pages in GROUPS:
        side += f'<div class="sgrp">{group}</div>'
        for k, t, h in pages:
            number += 1
            side += link(k, t, h, number)
    return side


def update_console() -> None:
    """Write the same menu into ui/index.html, between its <!--side--> markers."""
    path = os.path.join(HERE, "index.html")
    with open(path, encoding="utf-8", newline="") as handle:
        raw = handle.read()
    text = raw.replace("\r\n", "\n")
    new = re.sub(r"<!--side-->.*?<!--/side-->", lambda m: "<!--side-->" + side_html("scan") + "<!--/side-->", text, count=1, flags=re.S)
    if new != text:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(new.replace("\n", "\r\n") if "\r\n" in raw else new)
        print("updated ui/index.html menu")


def page(key: str, title: str, body: str, wide: bool = False, extra_head: str = "", script: str = "") -> str:
    side = side_html(key)
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
<header class="topbar"><div class="in"><a class="brand" href="/">{LOGO}Security Analyzer</a><span class="team">IPL Neural Navigators<i>&middot;</i>Cohort ICAIPM2026F</span></div></header>
<div class="shell"><aside class="side" aria-label="Pages">{side}</aside>
<main class="doc{' wide' if wide else ''}">{body}{pager}</main></div>{script}</body></html>"""


def write(name: str, html: str) -> None:
    path = os.path.join(OUT, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for attempt in range(20):  # on Windows a page that is being served or viewed can be briefly unwritable
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(html)
            break
        except OSError:
            if attempt == 19:
                raise
            time.sleep(0.1)
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


def plain(text: str) -> str:
    """A short plain-language box at the top of a page, for readers who want the idea before the detail."""
    return f'<div class="plain"><b>In plain words</b><p>{text}</p></div>'


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


def attr_data() -> dict | None:
    src = os.path.join(ROOT, "docs_html", "data", "attribution.json")
    if not os.path.isfile(src):
        return None
    with open(src, encoding="utf-8") as handle:
        return json.load(handle)


STAGE = {"auditor": "Auditor", "investigator": "Investigator", "fixer_validator": "Fixer & Validator"}


CAUSE_NOTE = {"15": " (the red-team notes trace the cause to the re-check scanning the whole file)"}


def eval_block(key: str) -> str:
    """'How it is evaluated', for the Agent design page. Built from evals/attribution.py and the last eval record."""
    a = attr_data()
    if not a:
        return ""
    stage = STAGE[key]
    judged = "".join(f"<li>{e(t[0].upper() + t[1:])}</li>" for t in a["judged_on"][stage])
    fails = a["failing"][stage]
    n = len(a["cases_run"])
    n_gold = sum(1 for c in a["cases_run"] if int(c.split("_")[1]) <= 11)
    n_red_all = sum(1 for c in G.CASES if int(c["id"].split("_")[1]) >= 12)
    where = (f"The {n} test cases that <code>python evals/run_evals.py</code> runs with the built-in agents (no AI model): the {n_gold} golden cases and {n - n_gold} of the {n_red_all} red-team attacks. "
             "The other attacks test a guardrail that normal agents never trigger, so <code>evals/redteam.py</code> runs them with an agent that misbehaves on purpose.")
    if fails:
        result = f"<p>In those cases a failure first showed up at this agent in {len(fails)}:</p><ul>" + "".join(f"<li><b>Case {e(x['case'].split('_')[1])}</b>: {e(x['why'])}{e(CAUSE_NOTE.get(x['case'].split('_')[1], ''))}</li>" for x in fails) + "</ul>"
    else:
        result = "<p>In those cases no failure first showed up at this agent.</p>"
    return (f'<h4 class="agentpart">How it is evaluated</h4><div class="md"><p>Every test case has an answer key. When a case fails, the failure is recorded at the first stage where it showed up, in pipeline order. This is a first-failure rule, not a root-cause finding.</p>'
            f'<p><b>It is judged on:</b></p><ul>{judged}</ul><p><b>Latest result.</b> {where}</p>{result}'
            f'<p class="small muted">All test cases and what happened in each: <a href="/docs/testing.html">Evals and testing</a>.</p></div>')


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
    body = lead("Problem and idea", "Security scanners list problems but leave the fixing to people. This agent team finds the weak spots, prepares a tested fix for each one, and lets a person decide.") + """
<p><a class="canvasbtn" href="/docs/canvas.html" data-canvas>View the project canvas</a><span class="small muted">The one-page design this project started from.</span></p>
""" + f"""
{prd_html(1, skip=("Why an agent and not a script",))}
<h2>The job and what success looks like</h2>
{prd_html(2)}
"""
    return page("summary", "Problem and idea", body, script='<dialog id="canvasdlg" class="canvasdlg"><div class="dlghead"><b>Project canvas</b><button type="button" id="canvasclose" aria-label="Close the canvas">&times;</button></div><iframe id="canvasframe" title="Project canvas"></iframe></dialog>\n<script>(function(){var d=document.getElementById("canvasdlg"),f=document.getElementById("canvasframe");\ndocument.querySelectorAll("[data-canvas]").forEach(function(a){a.addEventListener("click",function(ev){ev.preventDefault();if(f.getAttribute("data-ready")!=="1"){f.src=a.href;f.setAttribute("data-ready","1")}d.showModal()})});\ndocument.getElementById("canvasclose").onclick=function(){d.close()};\nd.addEventListener("click",function(ev){if(ev.target===d)d.close()})})();</script>')


AGENT_ORDER = (("auditor", "Auditor"), ("investigator", "Investigator"), ("fixer_validator", "Fixer and Validator"))


def agent_instructions(key: str) -> tuple:
    """(description, tools, markdown body) from agents/<key>.md: front matter read, title line dropped, headings one level down."""
    with open(os.path.join(ROOT, "agents", key + ".md"), encoding="utf-8") as handle:
        text = handle.read().replace("\r\n", "\n")
    desc = tools = ""
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if m:
        for line in m.group(1).split("\n"):
            if line.startswith("description:"):
                desc = line.split(":", 1)[1].strip()
            elif line.startswith("tools:"):
                tools = line.split(":", 1)[1].strip().strip("[]")
        text = text[m.end():]
    text = re.sub(r"(?m)^# .*\n", "", text, count=1)
    text = re.sub(r"(?m)^## ", "##### ", text)
    return desc, tools, text.strip()


def agent_section(key: str, title: str) -> str:
    desc, tools, body = agent_instructions(key)
    html_body = re.sub(r'<h5 id="([^"]+)"', lambda m: f'<h5 id="{key}-{m.group(1)}"', render_md(body))
    tool_list = ", ".join(f"<code>{e(t.strip())}</code>" for t in tools.split(",") if t.strip())
    return (f'<h3 class="agenthead" id="agent-{key}">{e(title)}</h3>'
            f'<div class="tw"><table><tr><td style="width:90px"><b>Decides</b></td><td>{e(desc)}</td></tr><tr><td><b>Tools</b></td><td>{tool_list}</td></tr></table></div>'
            f'<h4 class="agentpart">Instructions it is given</h4>'
            f'<p class="small muted">Sent to the agent at run time, from <code>agents/{key}.md</code>.</p>'
            f'<div class="md">{html_body}</div>' + eval_block(key))


def build_design() -> str:
    toc = "".join(f'<a href="#agent-{k}">{t}</a>' for k, t in AGENT_ORDER)
    sections = "".join(agent_section(k, t) for k, t in AGENT_ORDER)
    body = lead("Agent design", "Why this is an agent and not a script, who does what, how the agents are connected, and which agentic patterns are used.") + plain("Three small AI agents each do one job. The Auditor finds the problems, the Investigator works out the cause, and the Fixer and Validator writes and tests a fix. The orchestrator, a plain program and not an AI, runs them in a fixed order, and a person approves every fix.") + f"""
<h2>Why an agent</h2>
{prd_sub(1, "Why an agent and not a script")}
<h2>The three agents and how they work</h2>
{prd_sub(3, "Roles and tools")}
<div class="figure">{ARCH}</div>
<p>Every handoff goes through the orchestrator. The agents never call each other, and the original files are read only.</p>
<h2>Agentic patterns used</h2>
<div class="tw"><table><tr><th>Pattern</th><th>How</th></tr>
<tr><td>Multi-agent with an orchestrator</td><td>Three agents with separate jobs, coordinated by plain code.</td></tr>
<tr><td>Pipeline</td><td>A scan is seven fixed steps, in a fixed order.</td></tr>
<tr><td>Tool use with least privilege</td><td>Seven tools. Each agent gets only its own, through its own MCP profile.</td></tr>
<tr><td>Routing and hand-over</td><td>Each finding is routed: fix, retry, or hand to a person.</td></tr>
<tr><td>Reflection and retry</td><td>The rules run again on the fixed copy, and a failed fix gets one retry.</td></tr>
<tr><td>Human in the loop</td><td>A person approves, edits or rejects every fix.</td></tr></table></div>
<h2>The agents one by one</h2>
<p>For each agent: what it decides, its tools, the instructions it is given, and how it is evaluated.</p>
<div class="toc">{toc}</div>
{sections}
{related(("roster", "Roster: single or several agents"), ("AGENTS", "AGENTS.md: the team spec"))}
"""
    return page("design", "Agent design", body)


def build_behaves() -> str:
    body = lead("How a scan works", "How a scan runs, its inputs and outputs, which limits apply, and when it hands a finding to a person.") + plain("You give it a project. It makes a safe copy, finds weak spots, tries a fix on the copy, runs your own tests, and waits for you. Your files are never changed.") + f"""
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
<h2>Inputs</h2>
{prd_sub(3, "Inputs")}
<h2>The limits that stop a scan</h2>
{prd_sub(3, "Limits and default values")}
<h2>Outputs</h2>
{prd_sub(3, "Outputs")}
<h2>What each finding contains</h2>
{prd_sub(3, "What each finding carries")}
<h2>When it hands a finding to a person</h2>
{prd_sub(3, "When the agent hands over to a person")}
{related(("AGENTS", "AGENTS.md: scope, limits and decisions"), ("DEMO", "Demo script"))}
"""
    return page("behaves", "How a scan works", body)


def link_refs(html: str) -> str:
    """Make the references on the Guardrails page clickable: files go to the repository, cases to the Evals and testing page. Statuses become pills."""
    html = re.sub(r"<code>((?:tests|evals)/[\w./]+\.py|kill_checks\.py)</code>",
                  lambda m: f'<a href="{REPO}/blob/master/{m.group(1)}" target="_blank" rel="noopener"><code>{m.group(1)}</code></a>', html)

    html = re.sub(r"<td>No( \([^<]*\))?</td>", lambda m: f"<td>{pill('risk', 'No')}{m.group(1) or ''}</td>", html)
    html = re.sub(r"<td>By hand( \([^<]*\))?</td>", lambda m: f"<td>{pill('wait', 'By hand')}{m.group(1) or ''}</td>", html)
    html = html.replace("<td>Yes</td>", f"<td>{pill('ok', 'Yes')}</td>")

    def cases(m):
        return re.sub(r"\b(\d{2})\b", lambda n: f'<a href="/docs/testing.html#case-{n.group(1)}">{n.group(1)}</a>', m.group(0))

    html = re.sub(r"(?:red-team )?cases? \d{2}(?: and \d{2})?", cases, html)
    return html


def build_safe() -> str:
    body = (lead("Guardrails", "What can go wrong, and the guardrails that stop it.")
            + plain("An AI tool can invent things, obey instructions hidden in code, or break working code. Each risk below has a guard. The checks that stop a run at once are on the Kill criteria and rollback page.")
            + link_refs(prd_html(4)))
    return page("safe", "Guardrails", body)


def build_kill() -> str:
    body = (lead("Kill criteria and rollback", "When a run stops at once, and when the product owner decides to go back to the previous setup.")
            + plain("There are two safety nets. A kill criterion stops a single run immediately, and it is checked automatically. Rollback is a decision by the product owner, not an automatic switch: if the results get worse, they go back to the previous setup.")
            + "<h2>Kill criteria</h2>" + prd_sub(9, "Kill criteria: stop at once if the agent")
            + "<h2>Rollback</h2><p>The product owner decides to go back to the previous rules, prompts, model or scan-only mode if any of these happens. Nothing switches back automatically.</p>" + prd_sub(9, "Rollback: the product owner decides to go back to the previous rules, prompts, model or scan-only mode if"))
    return page("kill", "Kill criteria and rollback", body)


def red_counts() -> tuple:
    rows = P.REDTEAM_ROWS
    return sum(1 for r in rows if r[2] != "BROKE"), sum(1 for r in rows if r[2] == "BROKE")


def situations() -> str:
    """The 11 situations the canvas says the golden set must cover, taken from the cases' own categories."""
    items = "".join(f"<li><b>{c['id'].split('_')[1]}</b> {e(c['expected']['category'])}</li>" for c in G.CASES if int(c["id"].split("_")[1]) <= 11)
    return (f"<h3>The 11 golden situations</h3><p>The canvas lists 11 situations the test set must cover, and each golden case is one of them. "
            f"The red-team attacks (12 to 21) were added later to try to break the system.</p><ul>{items}</ul>")


def what_was_run() -> str:
    """One table: the 21 cases in three groups (golden, red team run with them, red team run on its own) and what happened."""
    a = attr_data()
    ran = {c.split("_")[1] for c in a["cases_run"]} if a else None
    groups = {"golden": [], "red_with": [], "red_alone": []}
    for c in G.CASES:
        num = c["id"].split("_")[1]
        _, label, _ = G.verdict(c)
        ok = label == "Matches" or label.startswith("Red-team: HELD")
        if int(num) <= 11:
            groups["golden"].append((num, ok))
        elif ran is None or num in ran:
            groups["red_with"].append((num, ok))
        else:
            groups["red_alone"].append((num, ok))

    def nums(items):
        return ", ".join(n for n, _ in items) or "-"

    def red(items):
        held = [n for n, ok in items if ok]
        broke = [n for n, ok in items if not ok]
        return f"{len(held)} held, {len(broke)} broke the system (broke: {', '.join(broke) or '-'})"

    g = groups["golden"]
    miss = [n for n, ok in g if not ok]
    rows = (f"<tr><td><b>Golden dataset</b><br><span class=\"small muted\">Realistic small projects, one for each of 11 situations</span></td><td>{nums(g)}</td><td><code>evals/run_evals.py</code></td>"
            f"<td>{len(g) - len(miss)} of {len(g)} pass (not passed: {', '.join(miss) or '-'})</td></tr>"
            f"<tr><td><b>Red-team attacks, run with the golden set</b><br><span class=\"small muted\">Cases written to break the system</span></td><td>{nums(groups['red_with'])}</td><td><code>evals/run_evals.py</code></td><td>{red(groups['red_with'])}</td></tr>"
            f"<tr><td><b>Red-team attacks, run on their own</b><br><span class=\"small muted\">They test a guardrail, so a misbehaving agent is swapped in</span></td><td>{nums(groups['red_alone'])}</td><td><code>evals/redteam.py</code></td><td>{red(groups['red_alone'])}</td></tr>")
    n_with = len(g) + len(groups["red_with"])
    return f"""<h2>What was run</h2>
<p>There are {len(G.CASES)} test cases, each with an answer key. {n_with} of them run together in <code>evals/run_evals.py</code>. The other {len(groups['red_alone'])} run on their own in <code>evals/redteam.py</code>, which swaps in an agent that does the bad thing on purpose, because the normal agents never would.</p>
<div class="tw"><table><tr><th>Set</th><th>Cases</th><th>Run with</th><th>What happened</th></tr>{rows}</table></div>
{situations()}
<p class="small muted">Both scripts were run by hand with the built-in agents (no AI model); there is no automatic pipeline yet. Ordinary code tests are separate: <code>python -m unittest discover -s tests</code> (176 tests). The per-agent view is on the <a href="/docs/design.html">Agent design</a> page.</p>
"""


def build_testing() -> str:
    body = lead("Evals and testing", "The test cases the agents are scored on, which ones ran, and what happened.") + f"""
{what_was_run()}
<h2>Each test case</h2>
{demote(strip_head(build_golden(inner=True)))}
{related(("RUN_SUMMARY", "Results of every check run"))}
"""
    return page("testing", "Evals and testing", body)


def build_results() -> str:
    held, broke = red_counts()
    live = demote(strip_head(build_live(inner=True))) if live_data() else ""
    body = lead("Results", "Where the agents stand against the quality bar, and what one real run with a model did.") + f"""
<h2>In short</h2>
<div class="tw"><table><tr><th>Status</th><th>What</th></tr>
<tr><td>{pill("ok", "Works")}</td><td>A scan runs end to end, the safety gates hold (no write to your files, evidence on every finding, all eight kill switches pass), and one live GPT-5 run fixed 7 of 10 findings for about $0.75 in about 19 minutes.</td></tr>
<tr><td>{pill("risk", "Not yet")}</td><td>The false-fix rate is 27% against a limit of 5%. This one matters most, because a wrong "verified" label can lead a person to approve a fix that leaves the hole open. Also, {broke} of 10 red-team attacks still break the system ({held} are stopped).</td></tr></table></div>
<h2>Quality standards</h2>
{prd_html(5)}
<h2>The live GPT-5 run</h2>
{live}
{related(("RUN_SUMMARY", "Results of every check run"))}
"""
    return page("results", "Results", body)


def build_pilot() -> str:
    body = lead("Pilot plan", "How the pilot starts and who takes part. The kill criteria and the rollback are on their own page.") + plain("A small trial with named reviewers, not a launch. It does not start until a model endpoint is approved and the false-fix check passes (see Limits and next steps).") + f"""
{prd_html(8)}
{related(("PILOT", "Pilot plan: setup, time comparison and rollback table"))}
"""
    return page("pilot", "Pilot plan", body)


def build_limits() -> str:
    held, broke = red_counts()
    body = lead("Limits and next steps", "What is not done yet, stated plainly, and what we would do next.") + plain("What is not done yet, and the order we would fix it in.") + f"""
<h2>What is not done yet</h2>
<div class="tw"><table><tr><th>Area</th><th>Where it stands</th></tr>
<tr><td>Red team</td><td>{broke} of 10 attacks still break the system. None is fixed yet.</td></tr>
<tr><td>Models and sample size</td><td>Only GPT-5 ran a full scan, and there is about one test case per type, so the scores show a direction, not a proof.</td></tr>
<tr><td>False-fix rate</td><td>27% against a limit of 5%. Not measured on the live run.</td></tr>
<tr><td>Time saved</td><td>Not measured. It needs real reviewers.</td></tr>
<tr><td>Judge model</td><td>Built, but only tested with a stub.</td></tr>
<tr><td>Cost and data handling</td><td>The price rates are unchecked, and tracing sends requests to a third-party service.</td></tr>
<tr><td>Pilot setup</td><td>The participants, repository and rules owner are not named.</td></tr></table></div>
<h2>Next steps, in order</h2>
<ol>
<li>Fix the four most serious red-team failures (secrets in run files, patches that edit tests, false fixes, missing usage counts) and run them again.</li>
<li>Score a model-backed run on all 21 cases.</li>
<li>Have a person label every approved fix as right or wrong, to get a real false-fix rate.</li>
<li>Record reviewer time and compare it with manual work.</li>
<li>Set up the judge model and check it against a person on at least 20 findings.</li>
<li>Confirm the price card, and approve the model provider and the tracing service.</li>
<li>Name the pilot participants, repository and rules owner, then start.</li></ol>
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


NUM = {sid: n for n, sid in enumerate([i for _, ids in PHASES for i in ids], 1)}  # shown as 1 to 15, in order


def prompt_item(sid: str, s: dict) -> str:
    """One step: its number and title, what it does (always visible), and the prompt itself behind a click."""
    n = P.NOTES[sid]
    title = re.sub(r"^(Step \d+|Prompt \d[A-C]) · ", "", s["heading"])
    prompt = "\n".join(l for l in s["prompt"] if not l.startswith("Using an existing repo instead"))
    plain_text = n["plain"].replace(" Section B of this page shows exactly what each agent prompt says and the real output each one produced.", "")
    return (f'<div class="step" id="step-{sid}"><div class="stephead"><span class="num">{NUM[sid]}</span><b>{e(title)}</b></div>'
            f'<p>{e(plain_text)}</p><details class="prompt"><summary>Show the prompt</summary><pre>{e(prompt)}</pre></details></div>')


def build_prompts() -> str:
    by_id = {}
    for s in P.steps:
        if s["prompt"]:
            by_id[P.step_id(s["heading"])] = s
    states = []
    parts = []
    for name, ids in PHASES:
        parts.append(f'<div class="phase">{e(name)}</div>' + "".join(prompt_item(i, by_id[i]) for i in ids))
    body = f"""<h1>How we built</h1>
<p class="lede">What it does, and the fifteen prompts used with Claude Code to build it, in the order they were run.</p>
<h2>What it does</h2>
<p>It scans a Python project for weak spots, proposes a fix for each, tests the fix in a temporary copy, then waits for you to approve, edit or reject it. It never changes your files.</p>
<div class="cards">
<div class="card"><h3>Finds</h3><p>SQL injection, command injection and path traversal. It also reports hard-coded secrets, weak password hashes and unpinned packages, but never fixes those.</p></div>
<div class="card"><h3>Proposes and tests</h3><p>Each fix is applied to a temporary copy, the project's own tests run, and the rules run again. A fix counts as verified only if both pass.</p></div>
<div class="card"><h3>Asks you</h3><p>Every fix waits for a person. Approved fixes are written to <code>fixes.patch</code>. You apply them yourself.</p></div>
</div>
<h2>The prompts</h2>
<p>Each step says what it does. Open <b>Show the prompt</b> to read the prompt itself.</p>
<p class="small muted">Each prompt produced code, tests and a commit. How well the result scores is on the <a href="/docs/results.html">Results</a> page, and the agents' instructions are on the <a href="/docs/design.html">Agent design</a> page.</p>
{"".join(parts)}
"""
    return page("prompts", "How we built", body)


# --------------------------------------------------------------------------- golden dataset
def build_golden(inner: bool = False) -> str:
    gold, red_with, red_alone = [], [], []
    n_pass = n_held = 0
    att = attr_data()
    ran = {c.split("_")[1] for c in att["cases_run"]} if att else None
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
        row = (f'<details class="item" id="case-{num}"><summary><span class="num">{num}</span><div class="sum"><b>{e(idx["category"])}</b><span>{e(idx["input"])}</span></div>{pill("ok" if passed else "risk", word)}</summary><div class="body">'
               f'<h4>Expected</h4><p>{e(idx["expected_output"])}</p><h4>What happened</h4><p>{e(why)}</p><h4>Why it is in the set</h4><p>{e(idx["why_in_set"])}</p>'
               f'<h4>Code</h4>{files}<p class="small faint mono">{e(c["id"])}</p></div></details>')
        if is_red:
            (red_alone if ran is not None and num not in ran else red_with).append((num, row))
            n_held += passed
        else:
            gold.append(row)
            n_pass += passed
    n_gold, n_red = len(gold), len(red_with) + len(red_alone)

    def attack_table(nums: list) -> str:
        rows = "".join(
            f'<tr><td>{a}</td><td>{e(b)}</td><td>{pill("risk" if c == "BROKE" else "ok", "Broke it" if c == "BROKE" else "Held")}</td><td>{e(d)}</td></tr>'
            for a, b, c, d in P.REDTEAM_ROWS if a in nums)
        return f'<div class="tw"><table><tr><th>Case</th><th>Attack</th><th>Result</th><th>What went wrong</th></tr>{rows}</table></div>'

    with_nums, alone_nums = [n for n, _ in red_with], [n for n, _ in red_alone]
    alone_block = ""
    if red_alone:
        alone_block = (f"<h2>Red-team cases run on their own ({', '.join(alone_nums)})</h2>"
                       "<p>These three test a guardrail, and the normal agents never do the bad thing that would trigger it. So <code>python evals/redteam.py</code> swaps in an agent that does it on purpose, to see whether the system stops it.</p>"
                       + attack_table(alone_nums) + "".join(r for _, r in red_alone))
    body = f"""<h1>The {n_gold + n_red} test cases</h1>
<p class="lede">The test cases are small projects with a known right answer. After each run we compare what the agents did with that answer.</p>

<h2>Golden cases (1 to {n_gold})</h2>
<p>Each one is graded against its answer key. <b>Pass</b> means the system found the expected problem and ended in the expected state: a fix ready for approval, handed to a person, or nothing reported for safe code. <b>Fail</b> means it did something else. Open a case to see what happened. The failures come from the built-in agents, which only handle some fix shapes; a model-backed agent is meant to close them.</p>
{"".join(gold)}

<h2>Red-team cases run with the golden set ({', '.join(with_nums)})</h2>
<p>These are attacks, so finding weaknesses is their job. <b>Held</b> means the system stopped the attack. <b>Broke it</b> means the attack got through a guardrail. Each weakness is recorded with the smallest fix we propose, and none is fixed yet. They run with <code>python evals/run_evals.py</code>.</p>
{attack_table(with_nums)}
{"".join(r for _, r in red_with)}
{alone_block}
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
        rows.append(f'<tr><td>{e(f["id"])}</td><td>{e(f["rule"])}</td><td><code>{e(f["file"])}:{f["line"]}</code></td><td>{pill(*outcome(f))}</td></tr>')
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
<p class="lede">What a real scan did when the three agents ran on {e(run["model"].upper())} against the demo project as it was then (10 findings; it has since grown to 13). Everything here is taken from that run's own report files. It is one run, not a benchmark.</p>

<div class="tiles">
<div class="tile"><b>{t["found"]}</b><span>findings</span></div>
<div class="tile"><b>{t["fixed_and_verified"]}</b><span>fixed and approved</span></div>
<div class="tile"><b>{t["needs_a_person"]}</b><span>left to a person</span></div>
<div class="tile"><b>{run["ai_calls"]}</b><span>AI calls, about {mins} minutes</span></div>
</div>
<p class="small muted">Run <code>{e(run["run_id"])}</code> on {e(run["date"])}. {run["tokens"]["input"]:,} input and {run["tokens"]["output"]:,} output tokens. What this costs is on the <a href="/docs/cost.html">Cost</a> page.</p>

<h2>1. What it found and did</h2>
<p>Each row is one finding. Open a finding below to see its fix attempts, test results and re-check.</p>
<div class="tw"><table><tr><th>Finding</th><th>Rule</th><th>Where</th><th>Outcome</th></tr>{"".join(rows)}</table></div>

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
</table></div>
"""
    return body if inner else page("live", "Live run", body)


# --------------------------------------------------------------------------- documents
DOCS = [
    ("Start here", [("README", "README.md", "What the project is and how to run it"), ("DEMO", "DEMO.md", "A four-run demo script with exact commands"), ("DEPLOY", "docs/DEPLOY.md", "How to host the console, and the risks")]),
    ("Decisions", [("AGENTS", "AGENTS.md", "The team spec: scope, roster, tools, limits"), ("roster", "docs/roster.md", "Single agent or several, and why the Auditor stays"), ("canvas", "canvas.md", "The original canvas: agents, tools, guardrails, quality bar, kill criteria"), ("cost", "docs/cost.md", "What a scan costs, measured on a live run")]),
    ("Pilot", [("PILOT", "docs/PILOT.md", "Pilot setup, kill criteria, rollback and scale-up")]),
    ("Review", [("RUN_SUMMARY", "docs/RUN_SUMMARY.md", "Results of every check run: tests, test cases, red team, kill switches, live model runs"), ("UX_REVIEW", "docs/UX_REVIEW.md", "UX review of the console and what changed")]),
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
    return page("canvas", "Canvas", body, wide=True, extra_head='<script>if(window.self!==window.top)document.documentElement.classList.add("embed")</script>')


COST_PAGE = r"""<h1>What a scan costs</h1>
<p class="lede">One real scan, measured: the agents ran on GPT-5 against the demo project as it was then (10 findings in 28 files; it has since grown to 13). Every number on this page comes from that run or is simple arithmetic on it.</p>

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
<h2>2. What the same tokens would cost on other models</h2>
<p>This takes the tokens the real run used (190,198 in, 46,280 out) and prices them at each provider's published rate. It is a price comparison, not a run: only GPT-5 was actually run.</p>
<div class="tw"><table><tr><th>Provider</th><th>Model</th><th>Input per 1M tokens</th><th>Output per 1M tokens</th><th>Cost of this run's tokens</th></tr>
<tr><td>OpenAI</td><td>gpt-5 (the model used in this run)</td><td>$1.25</td><td>$10.00</td><td><b>$0.70</b></td></tr>
<tr><td>Anthropic</td><td>Claude Sonnet 5.5</td><td>$2.00</td><td>$10.00</td><td><b>$0.84</b></td></tr>
<tr><td>Google</td><td>Gemini 3.8 Flash</td><td>$0.75, then $1.50 from 1 Jan 2027</td><td>$3.75, then $7.50 from 1 Jan 2027</td><td><b>$0.32</b>, then <b>$0.63</b></td></tr></table></div>
<h2>3. What it would cost at volume</h2>
<p>The same scan, repeated. Assumes 22 working days a month and the cost of this run for every scan (the run already includes the model re-reading its context and retrying, so no extra multiplier is added).</p>
<div class="tw"><table><tr><th>Scans per day</th><th>Scans per month</th><th>Tokens per month</th><th>Cost per month</th></tr>
<tr><td>5</td><td>110</td><td>26 million</td><td>about $83</td></tr>
<tr><td>20</td><td>440</td><td>104 million</td><td>about $330</td></tr>
<tr><td>100</td><td>2,200</td><td>520 million</td><td>about $1,650</td></tr></table></div>
<p class="small muted">A larger project, or one with more findings, costs more: on this run each finding used about 23,600 tokens.</p>
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
        write(f"md/{slug_}.html", page("documents", title, f'<p class="small"><a href="/docs/summary.html">Problem and idea</a> · <span class="faint">{e(path)}</span></p>{doc_body(text)}', wide=True))


def main() -> int:
    for name in ("guide.html", "measure.html", "quality.html", "live.html", "golden.html", "rollout.html", "rollback.html", "documents.html", os.path.join("md", "PRD.html"),
                 os.path.join("md", "auditor.html"), os.path.join("md", "investigator.html"), os.path.join("md", "fixer_validator.html"), os.path.join("md", "status.html")):
        old = os.path.join(OUT, name)                                    # pages that no longer exist
        if os.path.isfile(old):
            os.remove(old)
    write("summary.html", build_summary())
    write("design.html", build_design())
    write("behaves.html", build_behaves())
    write("safe.html", build_safe())
    write("kill.html", build_kill())
    write("testing.html", build_testing())
    write("results.html", build_results())
    write("pilot.html", build_pilot())
    write("limits.html", build_limits())
    write("run.html", build_run())
    write("prompts.html", build_prompts())
    write("canvas.html", build_canvas())
    write("cost.html", build_cost())
    build_documents()  # md/*.html: roster, results, pilot plan, deploy notes and the rest
    update_console()
    return 0


if __name__ == "__main__":
    sys.exit(main())
