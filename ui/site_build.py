"""Builds the Guide (ui/site/*.html) that the console serves at /docs. Standard library only.

    python ui/site_build.py

Pages: guide, prompts (how it was built), golden (the 21 test cases), documents (project documents, rendered from markdown).
Inputs: docs_html/data (the parsed playbook, status.md, commits, captured outputs, case results) and the repository's own .md files.
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
NAV = [("guide", "Guide", "guide.html"), ("prd", "PRD", "md/PRD.html"), ("cost", "Cost", "cost.html"), ("canvas", "Canvas", "canvas.html"), ("prompts", "How it was built", "prompts.html"), ("golden", "Test cases", "golden.html"), ("documents", "Documents", "documents.html")]
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
            out.append(common.md(val))
    html = "".join(out)
    html = re.sub(r'<pre([^>]*)>', r'<pre\1>', html)
    return html


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
def metrics_rows() -> str:
    ev = P.read(P.D, "captured", "s7_run_evals.txt")
    rows = []
    for l in ev.split("\n"):
        m = re.match(r"^\s+(PASS|FAIL|not measured)\s+(.*?)\s{2,}(\S+)\s+threshold (.*)$", l)
        if m:
            cls = {"PASS": "ok", "FAIL": "risk"}.get(m.group(1), "")
            rows.append(f"<tr><td>{pill(cls, {'PASS': 'Met', 'FAIL': 'Not met'}.get(m.group(1), 'Not measured'))}</td><td>{e(m.group(2))}</td><td>{e(m.group(3))}</td><td>{e(m.group(4))}</td></tr>")
    return "".join(rows)


def build_guide() -> str:
    red = P.read(P.D, "captured", "s8_redteam.txt")
    m = re.search(r"Summary: (\d+) held, (\d+) broke the system, of (\d+)", red)
    held, broke = (m.group(1), m.group(2)) if m else ("?", "?")
    body = f"""
<h1>How the Security Analyzer works</h1>
<p class="lede">It scans a Python project for weak spots, proposes a fix for each, tests the fix in a temporary copy, then waits for you to approve, edit or reject it. It never changes your files.</p>
<div class="toc"><a href="#does">What it does</a><a href="#works">How it works</a><a href="#built">How it was built</a><a href="#run">How to run it</a><a href="#model">Connect a model</a><a href="#stands">Where it stands</a></div>

<h2 id="does">What it does</h2>
<div class="cards">
<div class="card"><h3>Finds</h3><p>SQL injection, command injection and path traversal. It also reports hard-coded secrets, weak password hashes and unpinned packages, but never fixes those.</p></div>
<div class="card"><h3>Proposes and tests</h3><p>Each fix is applied to a temporary copy, the project's own tests run, and the rules run again. A fix counts as verified only if both pass.</p></div>
<div class="card"><h3>Asks you</h3><p>Every fix waits for a person. Approved fixes are written to <code>fixes.patch</code>. You apply them yourself.</p></div>
</div>

<h2 id="works">How it works</h2>
<div class="figure">{DIAGRAM}</div>
<p>A scan is seven fixed steps, run by the orchestrator:</p>
<ol>
<li>Check the rules file.</li><li>Fingerprint your files and make a temporary copy.</li><li>The Auditor scans the whole project and ranks the findings.</li>
<li>For each finding, the Investigator traces the cause and the Fixer and Validator writes and tests a patch.</li>
<li>You decide on each fix.</li><li>The orchestrator checks that your original files are unchanged.</li><li>It writes the log and the report.</li></ol>
<p>Three rules hold the design together. Each agent can use only its own tools. A fix is called verified by the orchestrator from test results, never by the agent's opinion. Anything the agent is unsure about goes to a person.</p>
<p>The <a href="/docs/canvas.html">canvas</a> is the original design: users, tools, guardrails, quality bar and kill criteria. The <a href="/docs/md/roster.html">roster document</a> explains why there are three agents and one plain-code orchestrator, and records the decision to keep the Auditor as an agent.</p>

<h2 id="built">How it was built</h2>
<p>The project was built with Claude Code, one prompt at a time, following a fifteen-prompt Build Playbook. Each prompt produced code, tests and a commit, and ended with a check you run before moving on.</p>
<ol>
<li><b>Foundations.</b> Project setup, the written spec, and the agent roster.</li>
<li><b>Contracts and tools.</b> JSON schemas for the shared state, seven tools, and an MCP server that gives each agent only its own tools.</li>
<li><b>Agents and workflow.</b> The shared state, the orchestrator, and three agents. No model endpoint is approved yet, so the agents are deterministic stand-ins that follow the same contracts.</li>
<li><b>Guardrails.</b> Containment (originals, secrets, hostile text in code, forbidden commands) and decision rules (evidence, "verified", limits, hand-over).</li>
<li><b>Measurement.</b> A scoring harness against 21 test cases, a red team of ten attacks, and a cost model.</li>
<li><b>Pilot gate.</b> Eight kill-switch checks and the pilot plan.</li>
</ol>
<p>The console you are using, and the optional model connection, were added afterwards. <a href="/docs/prompts.html">See each prompt and what it produced</a>.</p>

<h2 id="run">How to run it</h2>
<p>You need Python 3.11 or newer and one package: <code>pip install jsonschema</code>.</p>
<pre class="code" style="padding:12px 16px"><code>python ui/server.py              # then open http://127.0.0.1:8765
python -m unittest discover -s tests
python evals/run_evals.py        # score the 21 cases against the quality bar
python kill_checks.py --run      # the eight kill-switch checks</code></pre>
<p>The same scan from a terminal: <code>python -m orchestrator.cli run &lt;folder&gt; golden/rules.json</code>, then <code>finish</code> after a person edits <code>review_queue.json</code>.</p>
<p><b>Safety.</b> To check a fix, the project's own tests run on the machine that hosts the console. Host it only where that is acceptable, scan only code you trust, and put it behind a token if anyone else can reach it. <a href="/docs/md/DEPLOY.html">Hosting notes</a>.</p>

<h2 id="model">Connect a model</h2>
<p>By default the agents are offline stand-ins. To use a real model:</p>
<ol>
<li>Open <b>Agents</b> in the console and choose <b>Connect a model</b>. Enter the endpoint, model name and API key. Or put <code>AI_MODEL_ENDPOINT</code>, <code>AI_MODEL_NAME</code> and <code>ANTHROPIC_API_KEY</code> in a <code>.env</code> file and press <b>Use .env</b>.</li>
<li>Press <b>Test</b>. It sends one tiny message with no project data.</li>
<li>Tick the agents that should use the model and confirm that masked code is sent to the endpoint.</li>
<li>Run a scan. The trace shows how many calls and tokens each handoff used.</li></ol>
<p>The harness fills in the paths, rules file and test command itself. Secrets and personal data are masked before anything is sent. The Auditor can keep only findings the rules tool returned. The Fixer's test and re-check results come from the tools, not from the model. A patch that edits tests, requirements or the rules file is refused. The key is held in memory and never written to disk.</p>
<p><b>Not yet proven.</b> This layer is tested against a mock server that speaks the Anthropic Messages format. It has not been run against a live model. Only that format is supported; another provider needs an adapter in <code>agents/model_agents.py</code>.</p>

<h2 id="stands">Where it stands</h2>
<p>The numbers below are from the latest evaluation run, with the offline stand-in agents. They describe the plumbing and the stand-ins, not a model.</p>
<div class="tw"><table><tr><th></th><th>Measure</th><th>Result</th><th>Required</th></tr>{metrics_rows()}</table></div>
<ul>
<li><b>Red team:</b> {held} of 10 attacks were stopped and {broke} broke the system. None of the {broke} is fixed yet.</li>
<li><b>Kill switches:</b> all eight checks pass.</li>
<li><b>Tests:</b> 144 of 149 pass. The five that fail test symbolic links and only run on Windows.</li>
<li><b>Open:</b> a live model run, real reviewers, prices for the cost model, and the owner names in <code>docs/PILOT.md</code>.</li></ul>
<p>The percentages come from about one case per type, so treat them as a direction, not a measurement.</p>
<p><a href="/docs/documents.html">All project documents</a> · <a href="{REPO}">Repository</a></p>
"""
    return page("guide", "Guide", body)


# --------------------------------------------------------------------------- prompts
PHASES = [("Foundations", ["0", "1", "2"]), ("Contracts and tools", ["3", "4A", "4B", "4C"]), ("Agents and workflow", ["5"]),
          ("Guardrails", ["6A", "6B"]), ("Measurement", ["7A", "7B", "8", "9"]), ("Pilot gate", ["10"])]


def short(text: str, n: int = 190) -> str:
    text = text.strip()
    cut = text.split(". ")[0].rstrip(".") + "."
    return cut if len(cut) <= n else text[: n].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def lines(text: str, n: int) -> str:
    rows = text.strip().split("\n")
    return "\n".join(rows[:n]) + (f"\n… ({len(rows) - n} more lines)" if len(rows) > n else "")


def prompt_item(sid: str, s: dict) -> str:
    n = P.NOTES[sid]
    title = re.sub(r"^(Step \d+|Prompt \d[A-C]) · ", "", s["heading"])
    verdicts = [c[1] for c in n["checks"]]
    state = ("risk", "Not built") if verdicts.count(P.NO) == len(verdicts) else ("wait", "Partly shown") if P.NO in verdicts or P.PART in verdicts else ("ok", "Done")
    if sid == "5":
        state = ("wait", "Stand-in agents")
    commits = " ".join(f'<span class="pill">{h}</span>' for h in n["commits"])
    prompt = "\n".join(l for l in s["prompt"] if not l.startswith("Using an existing repo instead"))
    out = [f'<details class="item" id="step-{sid}"><summary><span class="num">{sid}</span><div class="sum"><b>{e(title)}</b><span>{e(short(n["plain"]))}</span></div>{pill(*state)}</summary><div class="body">']
    out.append(f'<h4>What it does</h4><p>{e(n["plain"])}</p>')
    chk = {P.OK: ("ok", "Shown"), P.PART: ("wait", "Partly"), P.NO: ("risk", "Not shown"), P.HUM: ("info", "Yours to do")}
    out.append('<h4>Checks before moving on</h4><div class="tw"><table>' + "".join(
        f'<tr><td style="width:110px">{pill(*chk[c[1]])}</td><td>{e(c[0])}<div class="small muted">{e(c[2])}</div></td></tr>' for c in n["checks"]) + "</table></div>")
    if sid == "8":
        out.append("<h4>The ten attacks</h4><div class='tw'><table><tr><th>Case</th><th>Attack</th><th>Result</th><th>What went wrong</th></tr>" + "".join(
            f'<tr><td>{a}</td><td>{e(b)}</td><td>{pill("risk" if c == "BROKE" else "ok", "Broke it" if c == "BROKE" else "Held")}</td><td>{e(d)}</td></tr>' for a, b, c, d in P.REDTEAM_ROWS) + "</table></div>")
    if sid == "10":
        out.append("<h4>The eight kill criteria</h4><div class='tw'><table><tr><th>Criterion</th><th>Enforced by</th></tr>" + "".join(
            f"<tr><td>{e(a)}</td><td>{e(b)}</td></tr>" for a, b, c in P.KILL) + "</table></div>")
    if n.get("note"):
        out.append(f'<h4>Note</h4><p>{e(n["note"])}</p>')
    if commits:
        out.append(f'<h4>Commits</h4><p>{commits}</p>')
    for ch in n["commits"]:
        c = P.COMMITS.get(ch)
        if c and c["body"]:
            out.append(f'<details><summary>What the coding agent reported in {ch}</summary><pre>{e(lines(c["body"], 40))}</pre></details>')
    for r in n["repro"]:
        text = P.captured(r)
        out.append(f'<details><summary>Output re-run here: <code>{e(text.split(chr(10))[0].replace("### ", ""))}</code></summary><pre>{e(lines(text, 45))}</pre></details>')
    out.append(f'<details><summary>The prompt as written in the playbook</summary><pre>{e(prompt)}</pre></details>')
    out.append("</div></details>")
    return "".join(out)


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
<p class="lede">Fifteen prompts, run one at a time in Claude Code. Open a prompt to see what it does, the checks that go with it, and what came out.</p>
<p class="small muted">Output comes from three places: your <code>status.md</code> and commit messages (the coding agent's own reports), documents it wrote into the repository, and commands re-run here against the repository so you can compare. Your original Claude Code transcripts are not in the repository, so they are not shown yet.</p>
{"".join(parts)}
<h2>The three agents' instructions</h2>
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
        rows.append(f'<details class="item" data-g="{grp}"><summary><span class="num">{num}</span><div class="sum"><b>{e(idx["category"])}</b><span>{e(idx["input"])}</span></div>{pill(cls_map.get(cls, "info"), label)}</summary><div class="body">'
                    f'<h4>Expected</h4><p>{e(idx["expected_output"])}</p><h4>What happened</h4><p>{e(why)}</p><h4>Why it is in the set</h4><p>{e(idx["why_in_set"])}</p>'
                    f'<h4>Code</h4>{files}<p class="small faint mono">{e(c["id"])}</p></div></details>')
    body = f"""<h1>The 21 test cases</h1>
<p class="lede">The golden dataset is the answer key. Cases 1 to 11 are the canvas types. Cases 12 to 21 are hostile inputs added for the red team.</p>
<div class="statline"><div><b>{counts['match']}</b><span>match the answer key</span></div><div><b>{counts['mismatch']}</b><span>differ from it</span></div><div><b>{counts['red']}</b><span>are red-team cases</span></div></div>
<p>Most mismatches have one cause: the offline stand-in Fixer can patch only one shape of SQL injection, so other findings end as "needs a person". A model-backed Fixer is the intended fix. The red-team cases are judged separately by <code>evals/redteam.py</code>.</p>
<div class="chips" role="group" aria-label="Filter"><button class="on" data-f="all">All</button><button data-f="match">Match</button><button data-f="mismatch">Differ</button><button data-f="red">Red team</button></div>
{"".join(rows)}"""
    script = """<script>document.querySelectorAll('.chips button').forEach(b=>b.onclick=()=>{document.querySelectorAll('.chips button').forEach(x=>x.classList.toggle('on',x===b));
document.querySelectorAll('.item[data-g]').forEach(d=>d.hidden=b.dataset.f!=='all'&&d.dataset.g!==b.dataset.f)})</script>"""
    return page("golden", "Test cases", body, script=script)


# --------------------------------------------------------------------------- documents
DOCS = [
    ("Start here", [("PRD", "docs/PRD.md", "The AI-native PRD: contract, quality bar, failure modes, eval plan, cost"), ("README", "README.md", "What the project is and how to run it"), ("DEMO", "DEMO.md", "A four-run demo script with exact commands"), ("DEPLOY", "docs/DEPLOY.md", "How to host the console, and the risks")]),
    ("Decisions", [("AGENTS", "AGENTS.md", "The team spec: scope, roster, tools, limits"), ("roster", "docs/roster.md", "Single agent or several, and why the Auditor stays"), ("canvas", "canvas.md", "The original canvas: agents, tools, guardrails, quality bar, kill criteria"), ("cost", "docs/cost.md", "Cost model and its assumptions")]),
    ("Pilot", [("PILOT", "docs/PILOT.md", "Pilot setup, kill criteria, rollback and scale-up")]),
    ("Agent instructions", [("auditor", "agents/auditor.md", "What the Auditor is told"), ("investigator", "agents/investigator.md", "What the Investigator is told"), ("fixer_validator", "agents/fixer_validator.md", "What the Fixer and Validator is told")]),
    ("Review", [("UX_REVIEW", "docs/UX_REVIEW.md", "UX review of the console and what changed"), ("status", "docs_html/data/status.md", "The coding agent's own build status report")]),
]


def build_canvas() -> str:
    with open(os.path.join(ROOT, "canvas.md"), encoding="utf-8") as handle:
        text = handle.read()
    html = render_md(re.sub(r"^\*(.+)\*$", r"\1", text, flags=re.M))
    note = ('<p class="small muted">This is the Agent Opportunity Canvas the project was built from (<code>canvas.md</code>). It is the source for the agent roles, tools, guardrails, quality bar and kill criteria. '
            'If it and another document disagree, the canvas and <a href="/docs/md/AGENTS.html">AGENTS.md</a> win until the team changes them.</p>')
    html = html.replace("</h1>", "</h1>" + note, 1)
    toc = []
    for level, title, sid in HEADINGS:
        if level == 1:
            continue
        toc.append(f'<a class="{"part" if level == 2 else ""}" href="#{sid}">{e(re.sub(r"[`*]", "", title))}</a>')
    body = f"""<div class="canvas"><nav class="ctoc" aria-label="Canvas sections"><b>The original canvas</b>{"".join(toc)}</nav>
<article class="md">{html}</article></div>"""
    return page("canvas", "Canvas", body, wide=True)


COST_PAGE = r"""<h1>Token cost at production volume</h1>
<p class="lede">Measured tokens per scan, scaled to the volume you expect. Enter your price card to get money. Nothing here is a quote.</p>
<div class="figure" style="padding:18px 20px"><div class="cgrid">
<div><label for="spd">Scans per day</label><input type="number" id="spd" value="20" min="0"></div>
<div><label for="wd">Working days per month</label><input type="number" id="wd" value="22" min="1" max="31"></div>
<div><label for="fps">Findings per scan</label><input type="number" id="fps" value="1" min="0" step="0.5"></div>
<div><label for="mult">Retry and context multiplier</label><input type="number" id="mult" value="3" min="1" step="0.5"></div>
<div><label for="pin">Input price per million tokens</label><input type="number" id="pin" min="0" step="any" placeholder="from your price card"></div>
<div><label for="pout">Output price per million tokens</label><input type="number" id="pout" min="0" step="any" placeholder="from your price card"></div>
<div><label for="cur">Currency</label><input type="text" id="cur" value="" placeholder="e.g. USD or INR"></div>
</div></div>
<div class="tiles" id="out"></div>
<h2>Three volumes</h2><div class="tw"><table id="scen"></table></div>
<h2>Where the numbers come from</h2>
<ul>
<li><b>Per scan, measured with the stand-in agents:</b> Auditor 2,016 in and 406 out; Investigator 934 in and 131 out; Fixer and Validator 1,777 in and 207 out. The Auditor runs once per scan. The other two run once per finding, so findings per scan scales them.</li>
<li><b>Token counts are a proxy</b> (characters divided by four), not the model's own count. Run <code>python evals/measure_handoffs.py --count-tokens</code> with an endpoint for real counts.</li>
<li><b>The multiplier of 3</b> is an assumption for context re-reads, retries and guardrail overhead. Replace it with the measured ratio after the first model runs.</li>
<li><b>Not included:</b> the person's review time, prompt caching or batch discounts, and larger repositories than the golden projects (one to three files). The rules scan costs no tokens.</li></ul>
<p><a href="/docs/md/cost.html">Full cost document</a> · <a href="/docs/md/PRD.html">PRD</a></p>
<style>.cgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:4px 18px}.cgrid label{margin-top:8px}</style>
<script>
const $=i=>document.getElementById(i), A={in:2016,out:406}, F={in:934+1777,out:131+207};
const fmt=n=>n>=1e6?(n/1e6).toFixed(2)+" M":Math.round(n).toLocaleString();
function calc(spd){const f=+$("fps").value||0,m=+$("mult").value||1,days=+$("wd").value||0;
 const inn=(A.in+f*F.in)*m,out=(A.out+f*F.out)*m,scans=spd*days,pin=parseFloat($("pin").value),pout=parseFloat($("pout").value);
 const priced=!isNaN(pin)&&!isNaN(pout),per=priced?(inn*pin+out*pout)/1e6:null;
 return{inn,out,scans,tin:inn*scans,tout:out*scans,per,month:priced?per*scans:null};}
function money(v){return v==null?"Enter prices":(($("cur").value||"")+" "+v.toLocaleString(undefined,{maximumFractionDigits:2})).trim()}
function draw(){const r=calc(+$("spd").value||0);
 $("out").innerHTML=[["Tokens per scan",fmt(r.inn+r.out),fmt(r.inn)+" in, "+fmt(r.out)+" out"],["Scans per month",Math.round(r.scans).toLocaleString(),""],
 ["Tokens per month",fmt(r.tin+r.tout),fmt(r.tin)+" in, "+fmt(r.tout)+" out"],["Cost per scan",money(r.per),""],["Cost per month",money(r.month),""]]
 .map(x=>`<div class="tile"><b>${x[1]}</b><span>${x[0]}${x[2]?" · "+x[2]:""}</span></div>`).join("");
 $("scen").innerHTML="<tr><th>Scans per day</th><th>Scans per month</th><th>Tokens per month</th><th>Cost per month</th></tr>"+[5,20,100].map(s=>{const q=calc(s);
 return`<tr><td>${s}</td><td>${Math.round(q.scans).toLocaleString()}</td><td>${fmt(q.tin+q.tout)}</td><td>${money(q.month)}</td></tr>`}).join("");}
document.querySelectorAll("input").forEach(i=>i.oninput=draw);draw();
</script>"""


def build_cost() -> str:
    return page("cost", "Cost at production volume", COST_PAGE)


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
            write(f"md/{slug_}.html", page("prd" if slug_ == "PRD" else "documents", title, f'<p class="small"><a href="/docs/documents.html">All documents</a> · <span class="faint">{e(path)}</span></p><div class="md">{render_md(text)}</div>', wide=True))
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
    write("documents.html", build_documents())
    return 0


if __name__ == "__main__":
    sys.exit(main())
