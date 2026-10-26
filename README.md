# Security Analyzer Agent
An agent that analyzes code for security issues, checked against a golden dataset of 11 cases.
The Agent Opportunity Canvas is in `canvas.md` (read-only).
Requires Python 3.11+ and the standard library only; `jsonschema` is the one approved package.
Run `python3 golden/verify_golden.py` from this folder to verify the golden dataset.

## Console and guide
- `python ui/server.py` opens the live console at http://127.0.0.1:8765 (needs `pip install jsonschema`). Guide pages are at `/docs`.
- The static site (recorded runs plus the guide) is published by `.github/workflows/pages.yml`; see `docs/DEPLOY.md`.
- `docs/PRD.md` is the product requirements document.
