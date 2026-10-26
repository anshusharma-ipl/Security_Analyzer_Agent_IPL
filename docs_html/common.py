"""Shared pieces for the two explainer pages: escaping, a tiny markdown renderer, CSS and JS. Standard library only."""
from __future__ import annotations

import re
from html import escape as e

CSS = r"""
:root{--bg:#f6f5f1;--panel:#fffefb;--ink:#17191c;--mute:#5d646e;--line:#e3e0d8;--accent:#0b6b63;--accent2:#b4531a;
--ok:#0b7a3b;--okbg:#e2f3e8;--warn:#85590a;--warnbg:#fbefcf;--bad:#a3241f;--badbg:#fbe5e3;--info:#1f4fa8;--infobg:#e5edfb;
--code:#efede6;--add:#e1f4e6;--del:#fbe9e7;--hl:#fff1a8;--nav:#fffefb}
@media (prefers-color-scheme:dark){:root{--bg:#101315;--panel:#171b1e;--ink:#e9ecee;--mute:#9aa3ac;--line:#2a3035;--accent:#4fd1c0;--accent2:#ffa361;
--ok:#63d58d;--okbg:#10301f;--warn:#efc05a;--warnbg:#332a0e;--bad:#ff8d88;--badbg:#3a1716;--info:#8cb2ff;--infobg:#15244a;
--code:#1f2528;--add:#11321f;--del:#3b1c1b;--hl:#4b4410;--nav:#14181a}}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:16px}
body{margin:0;background:var(--bg);color:var(--ink);font:15.5px/1.6 "Segoe UI",system-ui,-apple-system,sans-serif}
.wrap{display:grid;grid-template-columns:250px minmax(0,1fr);min-height:100vh}
nav.side{position:sticky;top:0;height:100vh;overflow:auto;background:var(--nav);border-right:1px solid var(--line);padding:20px 14px}
nav.side h2{font:600 12px/1 ui-monospace,Menlo,Consolas,monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--mute);margin:18px 8px 8px}
nav.side a{display:block;padding:5px 9px;border-radius:7px;color:var(--ink);text-decoration:none;font-size:13.5px;border-left:3px solid transparent}
nav.side a:hover{background:var(--code)}nav.side a.on{background:var(--code);border-left-color:var(--accent);font-weight:600}
nav.side .brand{font-weight:700;font-size:15px;padding:0 8px 4px}nav.side .brand small{display:block;color:var(--mute);font-weight:400;font-size:12px}
main{padding:34px clamp(16px,4vw,56px) 90px;max-width:1100px;width:100%}
@media (max-width:860px){.wrap{display:block}nav.side{position:static;height:auto;border-right:0;border-bottom:1px solid var(--line)}}
h1{font:700 clamp(26px,4vw,38px)/1.15 Georgia,"Iowan Old Style",serif;margin:0 0 10px;letter-spacing:-.01em}
h2.sec{font:700 24px/1.25 Georgia,"Iowan Old Style",serif;margin:52px 0 6px;padding-top:6px;border-top:2px solid var(--ink)}
h3{font-size:17px;margin:22px 0 6px}h4{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--mute);margin:18px 0 6px;font-family:ui-monospace,Menlo,Consolas,monospace}
.lede{font-size:17px;color:var(--mute);max-width:70ch;margin:0 0 18px}
p{margin:8px 0}a{color:var(--accent)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin:16px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:14px 0}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 14px}.stat b{display:block;font:700 28px/1.1 Georgia,serif}.stat span{color:var(--mute);font-size:13px}
.pill{display:inline-block;border-radius:999px;padding:1px 10px;font-size:12px;font-weight:700;white-space:nowrap;vertical-align:1px}
.ok{background:var(--okbg);color:var(--ok)}.warn{background:var(--warnbg);color:var(--warn)}.bad{background:var(--badbg);color:var(--bad)}.info{background:var(--infobg);color:var(--info)}.mute{background:var(--code);color:var(--mute)}
code,pre,.mono{font:12.8px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
code{background:var(--code);padding:1px 5px;border-radius:5px}
pre{background:var(--code);border-radius:9px;padding:12px 14px;overflow:auto;margin:8px 0;white-space:pre-wrap;word-break:break-word;max-height:520px}
pre.tall{max-height:none}
pre code{background:none;padding:0}
.diff span{display:block}.diff .a{background:var(--add)}.diff .d{background:var(--del)}.diff .h{color:var(--mute)}
table{border-collapse:collapse;width:100%;font-size:13.5px;margin:8px 0}
.tw{overflow-x:auto}
th,td{border-bottom:1px solid var(--line);padding:7px 10px;text-align:left;vertical-align:top}th{color:var(--mute);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
tr.m-bad td{background:var(--badbg)}
details{margin:10px 0}summary{cursor:pointer;font-weight:600;padding:4px 0}summary:hover{color:var(--accent)}
details.src{border:1px solid var(--line);border-radius:10px;padding:2px 14px;background:var(--panel)}
.tag{font:600 11px/1 ui-monospace,Menlo,monospace;letter-spacing:.05em;text-transform:uppercase;padding:3px 7px;border-radius:5px;margin-right:6px}
.t-user{background:var(--infobg);color:var(--info)}.t-commit{background:var(--code);color:var(--mute)}.t-repro{background:var(--warnbg);color:var(--warn)}.t-doc{background:var(--okbg);color:var(--ok)}
.step{border:1px solid var(--line);border-radius:14px;background:var(--panel);margin:26px 0;overflow:hidden}
.step>header{display:flex;flex-wrap:wrap;gap:10px 14px;align-items:center;padding:14px 20px;border-bottom:1px solid var(--line);background:linear-gradient(0deg,var(--panel),var(--code))}
.step>header .num{font:700 22px/1 Georgia,serif;color:var(--accent);min-width:2.1em}
.step>header h3{margin:0;font-size:18px;flex:1 1 260px}
.step .body{padding:6px 20px 18px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:18px}@media (max-width:900px){.cols{grid-template-columns:1fr}}
.check{list-style:none;padding:0;margin:6px 0}.check li{padding:7px 0 7px 30px;position:relative;border-bottom:1px dashed var(--line)}
.check li::before{content:"";position:absolute;left:0;top:11px;width:18px;height:18px;border-radius:50%;background:var(--mute)}
.check li.k-ok::before{background:var(--ok)}.check li.k-part::before{background:var(--warn)}.check li.k-no::before{background:var(--bad)}.check li.k-hum::before{background:var(--info)}
.check li small{display:block;color:var(--mute)}
.quote{border-left:3px solid var(--accent);padding:2px 0 2px 14px;margin:8px 0;color:var(--ink)}
.quote h5{margin:2px 0 4px;font-size:13px}
.src-md ul{padding-left:20px;margin:4px 0}.src-md h5{margin:10px 0 2px;font-size:13px;color:var(--mute)}
.copy{float:right;border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:7px;padding:3px 10px;font-size:12px;cursor:pointer}
textarea.note{width:100%;min-height:90px;border:1px solid var(--line);border-radius:9px;background:var(--bg);color:var(--ink);padding:9px;font:12.5px/1.5 ui-monospace,Menlo,Consolas,monospace}
.kbd{border:1px solid var(--line);border-bottom-width:2px;border-radius:5px;padding:0 6px;font:12px ui-monospace,monospace;background:var(--panel)}
.flow{display:flex;flex-wrap:wrap;gap:8px;align-items:stretch;margin:12px 0}
.flow div{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:8px 12px;font-size:13.5px;flex:1 1 140px}
.flow div b{display:block;font:600 11px/1.2 ui-monospace,monospace;color:var(--mute);letter-spacing:.06em;text-transform:uppercase}
.flow .agent{border-color:var(--accent)}.flow .person{border-color:var(--warn);background:var(--warnbg)}
.filters{display:flex;gap:6px;flex-wrap:wrap;margin:12px 0}.filters button{border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:999px;padding:5px 14px;font:inherit;font-size:13.5px;cursor:pointer}
.filters button.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.src-view{border:1px solid var(--line);border-radius:9px;overflow:auto;background:var(--code);margin:6px 0}
.src-view div{display:flex;white-space:pre;font:12.8px/1.6 ui-monospace,Menlo,Consolas,monospace}
.src-view i{font-style:normal;color:var(--mute);width:40px;text-align:right;padding-right:10px;flex:none;user-select:none}
.src-view .hit{background:var(--hl)}
.ftabs{display:flex;gap:4px;flex-wrap:wrap;margin-top:8px}.ftabs button{border:1px solid var(--line);background:var(--panel);color:var(--ink);padding:3px 10px;border-radius:7px;font:12px ui-monospace,monospace;cursor:pointer}.ftabs button.on{background:var(--accent);color:var(--bg);border-color:var(--accent)}
.note-sm{color:var(--mute);font-size:13px}
@media print{nav.side{display:none}.wrap{display:block}details{display:block}}
"""

JS = r"""
document.querySelectorAll('.copy').forEach(b=>b.onclick=()=>{const t=document.getElementById(b.dataset.for).innerText;navigator.clipboard&&navigator.clipboard.writeText(t).then(()=>{b.textContent='Copied';setTimeout(()=>b.textContent='Copy',1200)})});
const links=[...document.querySelectorAll('nav.side a[href^="#"]')];
const secs=links.map(a=>document.querySelector(a.getAttribute('href'))).filter(Boolean);
const io=new IntersectionObserver(es=>{es.forEach(x=>{if(x.isIntersecting){links.forEach(l=>l.classList.toggle('on',l.getAttribute('href')==='#'+x.target.id))}})},{rootMargin:'-20% 0px -70% 0px'});
secs.forEach(s=>io.observe(s));
document.querySelectorAll('textarea.note').forEach(t=>{const k='saa-note-'+location.pathname+t.dataset.k;try{t.value=localStorage.getItem(k)||''}catch(e){}t.oninput=()=>{try{localStorage.setItem(k,t.value)}catch(e){}}});
const ex=document.getElementById('exportNotes');if(ex)ex.onclick=()=>{const o={};document.querySelectorAll('textarea.note').forEach(t=>{if(t.value.trim())o[t.dataset.k]=t.value});const b=new Blob([JSON.stringify(o,null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='claude-code-outputs.json';a.click()};
"""


def shell(title: str, brand: str, sub: str, nav: list[tuple[str, str]], body: str) -> str:
    links = "".join(f'<a href="#{i}">{e(t)}</a>' for i, t in nav)
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{e(title)}</title><style>{CSS}</style></head><body><div class="wrap">'
            f'<nav class="side"><div class="brand">{e(brand)}<small>{e(sub)}</small></div>{links}</nav>'
            f'<main>{body}</main></div><script>{JS}</script></body></html>')


def pre(text: str, cls: str = "", pid: str | None = None) -> str:
    idattr = f' id="{pid}"' if pid else ""
    return f'<pre class="{cls}"{idattr}>{e(text)}</pre>'


def diff(text: str) -> str:
    rows = []
    for line in text.rstrip("\n").split("\n"):
        c = "a" if line.startswith("+") and not line.startswith("+++") else "d" if line.startswith("-") and not line.startswith("---") else "h"
        rows.append(f'<span class="{c}">{e(line) or "&nbsp;"}</span>')
    return '<pre class="diff tall">' + "".join(rows) + "</pre>"


def _inline(s: str) -> str:
    s = e(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    return s


def md(text: str) -> str:
    """Small markdown subset: headings, bullets, numbered lists, tables, paragraphs, fenced code."""
    out, lines, i = [], text.split("\n"), 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append(pre("\n".join(lines[i + 1:j]), "tall"))
            i = j + 1
            continue
        if ln.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
            head = [c.strip() for c in ln.strip().strip("|").split("|")]
            rows, j = [], i + 2
            while j < len(lines) and lines[j].startswith("|"):
                rows.append([c.strip() for c in lines[j].strip().strip("|").split("|")])
                j += 1
            out.append("<table><tr>" + "".join(f"<th>{_inline(h)}</th>" for h in head) + "</tr>" +
                       "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in rows) + "</table>")
            i = j
            continue
        m = re.match(r"^(#{1,6})\s+(.*)", ln)
        if m:
            out.append(f"<h5>{_inline(m.group(2))}</h5>")
            i += 1
            continue
        if re.match(r"^\s*[-*]\s+", ln) or re.match(r"^\s*\d+\.\s+", ln):
            ordered = bool(re.match(r"^\s*\d+\.", ln))
            items, j = [], i
            while j < len(lines) and (re.match(r"^\s*[-*]\s+", lines[j]) or re.match(r"^\s*\d+\.\s+", lines[j]) or (lines[j].startswith("  ") and items)):
                if re.match(r"^\s*([-*]|\d+\.)\s+", lines[j]):
                    items.append(re.sub(r"^\s*([-*]|\d+\.)\s+", "", lines[j]))
                else:
                    items[-1] += " " + lines[j].strip()
                j += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + f"</{tag}>")
            i = j
            continue
        if not ln.strip():
            i += 1
            continue
        j = i
        para = []
        while j < len(lines) and lines[j].strip() and not lines[j].startswith(("|", "```", "#")) and not re.match(r"^\s*([-*]|\d+\.)\s+", lines[j]):
            para.append(lines[j].strip())
            j += 1
        out.append(f"<p>{_inline(' '.join(para))}</p>")
        i = max(j, i + 1)
    return "".join(out)
