"""Builds ui/replay/replay.html: the real console UI playing back recorded runs, as ONE static file (no server).

    python ui/replay/record.py     # needs the console running; refreshes recorded.json
    python ui/replay/build.py

It reuses ui/index.html and ui/static/app.css, so the replay always looks like the live console.
Written for the Artifact tool: no doctype/html/head/body tags. Nothing executes in the replay.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
UI = os.path.dirname(HERE)
read = lambda *p: open(os.path.join(*p), encoding="utf-8").read()  # noqa: E731

css = read(UI, "static", "app.css")
dark = re.search(r"@media \(prefers-color-scheme:dark\)\{:root:not\(\[data-theme=light\]\)\{(.*?)\}\}", css, re.S).group(1)
html = read(UI, "index.html")
rec = read(HERE, "recorded.json")

body = html[html.index('<header class="topbar">'):html.index("<script>")]
body = body.replace('<a class="brand" href="/">', '<a class="brand" href="#top">')
NAVLINKS = [("Guide", "guide.html"), ("PRD", "md/PRD.html"), ("Cost", "cost.html"), ("Canvas", "canvas.html"), ("How it was built", "prompts.html"), ("Test cases", "golden.html")]
nav = '<nav class="nav" aria-label="Main"><a href="#top" aria-current="page">Scan (recorded)</a>' + "".join(f'<a href="docs/{h}">{t}</a>' for t, h in NAVLINKS) + "</nav>"
body = re.sub(r'<nav class="nav".*?</nav>', nav, body, flags=re.S)
body = re.sub(r'<div class="notice">.*?</div>', '<div class="notice"><span><b>Replay of real runs.</b> Pick a sample and press Run scan to play back a recorded run made with the offline stand-in agents. Nothing executes in this page. To scan your own code, run the live console from the repository.</span></div>', body, count=1, flags=re.S)
body = re.sub(r'<div class="footer">.*?</div>', '<div class="footer">Live console: <a href="https://github.com/anshusharma-ipl/Security_Analyzer_Agent_IPL" target="_blank" rel="noopener">repository</a></div>', body, flags=re.S)
body = body.replace('<a class="small" href="/docs/guide.html">How to connect a model</a>', "")
body = body.replace('<a class="small" href="/docs/guide.html">Read how it works</a>', "")
body = body.replace('<p class="small"><a href="/docs/guide.html">Read how it works</a></p>', "")
body = re.sub(r'<a class="small" href="/docs/guide.html#model">.*?</a>', "", body)

main_js = html[html.index("<script>") + 8:html.rindex("</script>")]
shim = r"""
/* ---- replay: serve the recorded runs instead of a server ---- */
const REC = __REC__;
let RCUR = null, RSTAGE = 0;
const jres = (obj, status = 200) => new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json" } });
const realFetch = window.fetch.bind(window);
window.fetch = async (url, opts = {}) => {
  const u = new URL(url, "http://replay.local"), p = u.pathname, method = (opts.method || "GET").toUpperCase();
  await new Promise((r) => setTimeout(r, 250));
  if (p === "/api/info") return jres(REC.info);
  if (p === "/api/model" && method === "GET") return jres(REC.info.model);
  if (p.startsWith("/api/model") || p.startsWith("/api/upload")) return jres({ error: "Not available in the replay. Run the live console to connect a model or upload code." }, 400);
  if (p === "/api/jobs" && method === "POST") {
    const body = JSON.parse(opts.body || "{}");
    RCUR = REC.cases[body.case]; RSTAGE = 0;
    if (!RCUR) return jres({ error: "That sample was not recorded." }, 400);
    return jres({ job_id: "replay" });
  }
  if (p === "/api/jobs/replay" && RCUR) return jres(RCUR.views[Math.min(RSTAGE, RCUR.views.length - 1)]);
  if (p === "/api/jobs/replay/review" && method === "POST") {
    const sent = JSON.parse(opts.body || "{}").decisions || [];
    if (RCUR.views.length < 2) return jres({ error: "Nothing to review." }, 409);
    RSTAGE = 1; window.__reviewer = sent[0]?.reviewer || "";
    return jres({ ok: true });
  }
  if (p === "/api/jobs/replay/file" && RCUR) {
    const path = u.searchParams.get("path"); return RCUR.files[path] != null ? jres({ path, text: RCUR.files[path] }) : jres({ error: "not found" }, 404);
  }
  return jres({ error: "Not available in the replay." }, 404);
};
""".replace("__REC__", rec)
after = r"""
/* ---- replay: downloads and approver name ---- */
{
  const origDone = window.donePanel;
  window.donePanel = (v) => origDone(v).replace(/<div class="dl">[\s\S]*?<\/div>/, '<p class="small muted">Report, fixes.patch and the decision log download from the live console.</p>');
}
"""
extra_css = """
#srcTabs,#tab-zip,#tab-dir,#modelDet,#mUse,.side details.plain,#idle .small{display:none}
.page{padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
.topbar .in,.footer{padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
.topbar{top:env(safe-area-inset-top,0px)}
body::before{content:"";position:fixed;inset:0 0 auto;height:env(safe-area-inset-top,0px);z-index:30;background:var(--surface)}
:root[data-theme="dark"]{%s color-scheme:dark}
@media (max-width:640px){.topbar .in{gap:14px}.mode{display:none}}
""" % dark

out = f"""<title>Security Analyzer Console</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Public+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
{css}
{extra_css}
</style>
<div id="top"></div>
{body}
<script>
{shim}
{main_js}
{after}
</script>
"""
with open(os.path.join(HERE, "replay.html"), "w", encoding="utf-8", newline="\n") as handle:
    handle.write(out)
print("wrote ui/replay/replay.html", len(out) // 1024, "KB")
