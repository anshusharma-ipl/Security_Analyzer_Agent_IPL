"""Builds a static copy of the Guide for a static host, next to replay.html.

    python ui/replay/build_static.py OUT_DIR

Writes OUT_DIR/index.html (the console replay) and OUT_DIR/docs/**.html with relative links and the stylesheet inlined.\nRun build.py and ../site_build.py first. Used by .github/workflows/pages.yml for GitHub Pages.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
UI = os.path.dirname(HERE)
out = sys.argv[1]
site = os.path.join(UI, "site")
css = open(os.path.join(UI, "static", "app.css"), encoding="utf-8").read()
dark = re.search(r"@media \(prefers-color-scheme:dark\)\{:root:not\(\[data-theme=light\]\)\{(.*?)\}\}", css, re.S).group(1)
css += ':root[data-theme="dark"]{%s color-scheme:dark}' % dark
ROOT_PAGE_ENV = os.environ.get("ROOT_PAGE_URL")
for dirpath, _, names in os.walk(site):
    for name in names:
        if not name.endswith(".html"):
            continue
        src = os.path.join(dirpath, name)
        rel = os.path.relpath(src, site)
        up = "../" * rel.count(os.sep)
        ROOT_PAGE = ROOT_PAGE_ENV or up + "../index.html"
        blank = ' target="_blank" rel="noopener"' if ROOT_PAGE_ENV else ""
        text = open(src, encoding="utf-8").read()
        text = text.replace('<link rel="stylesheet" href="/static/app.css">', f"<style>{css}</style>")
        text = text.replace('<a href="/">Scan</a>', f'<a href="{ROOT_PAGE}"{blank}>Scan</a>').replace('<a class="brand" href="/">', f'<a class="brand" href="{ROOT_PAGE}"{blank}>')
        text = re.sub(r'href="/docs/([^"]*)"', lambda m: f'href="{up}{m.group(1)}"', text)
        text = text.replace('href="/"', f'href="{ROOT_PAGE}"')
        dest = os.path.join(out, "docs", rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        open(dest, "w", encoding="utf-8", newline="\n").write(text)
# the console replay is the home page; it is written for the artifact viewer, so add what a normal page needs
replay = open(os.path.join(HERE, "replay.html"), encoding="utf-8").read()
head = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
replay = replay.replace("<style>\n", "<style>\n", 1).replace("</style>", ":root[data-theme=\"dark\"]{color-scheme:dark}\nbody{margin:0}</style>", 1)
open(os.path.join(out, "index.html"), "w", encoding="utf-8", newline="\n").write(head + replay)
open(os.path.join(out, ".nojekyll"), "w").write("")
print("wrote", out)
