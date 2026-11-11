# docs_html/

Inputs for the Guide that the console serves at `/docs`. The pages themselves are built by `ui/site_build.py` into `ui/site/`.

    python docs_html/collect_cases.py   # re-runs every golden case and writes data/cases_data.json
    python ui/site_build.py             # rebuilds the Guide, Evaluation, Canvas, prompts, test cases and documents

- `data/` holds the parsed playbook (the fifteen prompts), the coding agent's `status.md`, two captured outputs (`s4c_golden_table`, `s8_redteam`) and the case results (`cases_data.json`).
- `build_prompts.py` holds the prompt notes, agent summaries and red-team rows that `site_build.py` imports; `build_golden.py` holds the case verdict logic.
