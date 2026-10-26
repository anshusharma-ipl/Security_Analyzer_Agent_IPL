"""Standalone HTML version of a finished run's report (one file, no network, opens anywhere).

Built only from report.json (and state.json for the handoff trace). Every value is escaped; nothing is executed.
"""
from __future__ import annotations

from html import escape as e

STATUS_LABEL = {
    "verified_awaiting_approval": ("Fix verified", "ok"),
    "needs_a_person": ("Needs a person", "warn"),
    "rejected": ("Rejected", "bad"),
    "not_processed": ("Not processed", "mute"),
}
CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#14181f;--mute:#5b6472;--line:#e2e6ec;--ok:#0b7a3b;--okbg:#e4f5ec;--warn:#8a5a00;--warnbg:#fff3d6;
--bad:#a3201f;--badbg:#fde8e7;--add:#e6f6ea;--del:#fdecec;--code:#f1f3f6}
@media (prefers-color-scheme:dark){:root{--bg:#0f1318;--card:#171c23;--ink:#e8ebf0;--mute:#98a2b1;--line:#2a313b;--ok:#5fd18b;--okbg:#10301f;
--warn:#f0c15a;--warnbg:#33290e;--bad:#ff8c88;--badbg:#3a1615;--add:#11301d;--del:#3a1b1b;--code:#1e242d}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:980px;margin:0 auto;padding:28px 16px 60px}h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:30px 0 10px}
.sub{color:var(--mute);margin:0 0 20px}.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}.tile b{display:block;font-size:26px}
.tile span{color:var(--mute);font-size:13px}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:12px 0}
.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center}.pill{border-radius:999px;padding:2px 10px;font-size:12px;font-weight:600}
.ok{background:var(--okbg);color:var(--ok)}.warn{background:var(--warnbg);color:var(--warn)}.bad{background:var(--badbg);color:var(--bad)}
.mute{background:var(--code);color:var(--mute)}code,pre{font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
pre{background:var(--code);border-radius:8px;padding:10px 12px;overflow:auto;margin:8px 0;white-space:pre-wrap;word-break:break-word}
.diff .a{background:var(--add);display:block}.diff .d{background:var(--del);display:block}.diff .h{color:var(--mute);display:block}
dl{display:grid;grid-template-columns:150px 1fr;gap:4px 12px;margin:10px 0}dt{color:var(--mute)}dd{margin:0}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
th{color:var(--mute);font-weight:600}.note{color:var(--mute);font-size:13px}@media print{body{background:#fff}}
"""


def _diff(text: str) -> str:
    rows = []
    for line in text.rstrip("\n").split("\n"):
        cls = "a" if line.startswith("+") and not line.startswith("+++") else \
              "d" if line.startswith("-") and not line.startswith("---") else "h"
        rows.append(f'<span class="{cls}">{e(line) or "&nbsp;"}</span>')
    return '<pre class="diff">' + "".join(rows) + "</pre>"


def render_report_html(report: dict, state: dict) -> str:
    t, run = report["totals"], report["run"]
    out = [f"<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
           f"<title>Security Analyzer report</title><style>{CSS}</style><main>",
           "<h1>Security Analyzer report</h1>",
           f"<p class=sub>Outcome: <b>{e(report['outcome'])}</b> · rules file <code>{e(run['rules_file_version'][:23])}…</code> · "
           f"AI model: {e(run['ai_model']['name'])} · sensitive items hidden: {run['sensitive_items_hidden']} · "
           f"tokens {run['tokens']['input']} in / {run['tokens']['output']} out</p>",
           '<div class="tiles">']
    for label, key in (("Found", "found"), ("Fixed and verified", "fixed_and_verified"), ("Needs a person", "needs_a_person"),
                       ("Rejected", "rejected"), ("Not processed", "remaining")):
        out.append(f'<div class="tile"><b>{t[key]}</b><span>{label}</span></div>')
    out.append("</div>")
    if state.get("originals_unchanged") is not None:
        ok = state["originals_unchanged"]
        out.append(f'<div class="card"><span class="pill {"ok" if ok else "bad"}">{"Originals unchanged" if ok else "ORIGINALS CHANGED"}</span> '
                   "Every original file was fingerprinted before the run and compared again at the end. "
                   "Nothing was applied to the project; approved fixes are in <code>fixes.patch</code> for a person to apply.</div>")
    out.append("<h2>Findings</h2>")
    if not report["findings"]:
        out.append('<div class="card">No finding had proof (file, line and code). Nothing to report.</div>')
    for f in report["findings"]:
        label, cls = STATUS_LABEL.get(f["status"], (f["status"], "mute"))
        out.append(f'<div class="card"><div class="row"><b>{e(f["finding_id"])} · {e(f["rule_id"])}</b>'
                   f'<span class="pill {cls}">{label}</span><span class="pill mute">{e(f["severity"])}</span>'
                   f'<code>{e(f["file"])}:{f["line"]}</code></div>'
                   f'<pre>{e(f["evidence"]["quoted_code"])}</pre><dl>'
                   f'<dt>Confidence</dt><dd>{f["confidence"]} ({e(f["detected_by"])})</dd>'
                   f'<dt>Tests</dt><dd>before {e(str(f["tests"]["before"]))}, after {e(str(f["tests"]["after"]))}</dd>'
                   f'<dt>Re-check</dt><dd>{e(f["recheck"])}</dd>')
        if f.get("reason"):
            out.append(f'<dt>Reason</dt><dd>{e(f["reason"])}</dd>')
        if f.get("traced_cause"):
            tc = f["traced_cause"]
            path = " → ".join(tc["path"]) if tc.get("path") else ""
            out.append(f'<dt>Traced cause</dt><dd>{e(tc["explanation"])}' + (f"<br><code>{e(path)}</code>" if path else "") + "</dd>")
        out.append(f'<dt>Residual risk</dt><dd>{e(f["residual_risk"])}</dd></dl>')
        if f.get("patch_diff"):
            out.append(_diff(f["patch_diff"]))
        out.append("</div>")
    out.append("<h2>Approvals</h2>")
    if report["approvals"]:
        out.append("<table><tr><th>Finding</th><th>Decision</th><th>Reviewer</th><th>Reason</th><th>When</th></tr>")
        for a in report["approvals"]:
            out.append(f"<tr><td>{e(a['finding_id'])}</td><td>{e(a['decision'])}</td><td>{e(str(a['reviewer']))}</td>"
                       f"<td>{e(a['reason'] or '')}</td><td>{e(str(a['timestamp']))}</td></tr>")
        out.append("</table>")
    else:
        out.append('<div class="card">No fix was waiting for a decision.</div>')
    if state.get("handoff_log"):
        out.append("<h2>Handoff trace</h2><table><tr><th>Step</th><th>Agent</th><th>Job</th><th>Finding</th><th>Result</th><th>Wrote</th></tr>")
        for h in state["handoff_log"]:
            out.append(f"<tr><td>{h['step']}</td><td>{e(h['agent'])}</td><td>{e(h['job'])}</td><td>{e(h['finding_id'] or '-')}</td>"
                       f"<td>{e(h['result'])}</td><td>{e(', '.join(h['wrote']))}</td></tr>")
        out.append("</table>")
    out.append("<h2>Decision log</h2><table><tr><th>#</th><th>Actor</th><th>Event</th><th>Detail</th></tr>")
    for entry in report["audit_log"]:
        out.append(f"<tr><td>{entry['seq']}</td><td>{e(entry['actor'])}</td><td>{e(entry['event'])}</td><td>{e(entry['detail'])}</td></tr>")
    out.append("</table><p class=note>Generated by the Security Analyzer console. Agents are offline stand-ins unless a model endpoint is configured.</p></main></html>")
    return "".join(out)
