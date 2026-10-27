# Security Analyzer Agent
An agent team that checks a Python project against an approved rules file, prepares a tested fix for each finding in a temporary copy, and hands every fix to a person to approve. It never changes your files, never commits and never deploys.

The Agent Opportunity Canvas is in `canvas.md` (read-only). `AGENTS.md` holds the team decisions.
Requires Python 3.11+ and the standard library only; `jsonschema` is the one approved package.

## Try it
- `python ui/server.py` (or double-click `start.bat`, or run `start.sh`) opens the console at http://127.0.0.1:8765. Choose **Use the demo project** and **Run scan**: no key and no model needed. Needs `pip install jsonschema`.
- To use a model, pick OpenAI (GPT), Anthropic (Claude) or Google (Gemini) in the console and paste a key. Use fake or non-sensitive code until your security team has approved the provider. See `ui/README.md`.
- From a terminal: `python -m orchestrator.cli run <folder> golden/rules.json`, then `finish` after a person edits `review_queue.json`.

## What is in the repository
- `canvas.md`, `AGENTS.md`, `docs/PRD.md`, `docs/PILOT.md`: the design, the decisions, the product requirements and the pilot plan.
- `agents/`, `orchestrator/`, `tools/`, `schemas/`: the three agents (prompts, a built-in version and a model-backed version), the plain-code orchestrator, the seven tools and the JSON contracts.
- `golden/`: 21 cases with answer keys (the 11 from the canvas plus 10 red-team cases). `golden/verify_golden.py` checks that each case's tests behave as its key says. `golden/rules.json` is the sample rules file.
- `demo/shop_demo` (and `shop_demo.zip`): a sample project with all six rule types and three safe files. `DEMO.md` is the presenter script.
- `evals/`: `run_evals.py` (the quality bar), `redteam.py` (ten hostile inputs), the judge, cost and token measurements.
- `kill_checks.py`: the eight automatic kill switches.
- `ui/`: the console and the guide pages served at `/docs`. The static site is published by `.github/workflows/pages.yml`; see `docs/DEPLOY.md`.
- `docs/`: `RUN_SUMMARY.md` (results of every run), `cost.md`, `roster.md`, `UX_REVIEW.md`, `status.md`.

## Checks
- `python -m unittest discover -s tests`: the full test suite.
- `python evals/run_evals.py`, `python evals/redteam.py`, `python kill_checks.py --run`: scores, hostile inputs, kill switches.
- `python3 golden/verify_golden.py`: the golden dataset.
