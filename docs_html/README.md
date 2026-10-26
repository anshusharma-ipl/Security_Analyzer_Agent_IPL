# docs_html/

Inputs for the Guide that the console serves at `/docs`. The pages themselves are built by `ui/site_build.py` into `ui/site/`.

    python docs_html/collect_cases.py   # re-runs every golden case and writes data/cases_data.json
    python ui/site_build.py             # rebuilds the Guide, Evaluation, Canvas, prompts, test cases and documents

- `data/` holds the parsed playbook, `status.md`, commit messages, captured command outputs and case results.
- `build_prompts.py` and `build_golden.py` hold the per-step notes and case verdict logic that `site_build.py` imports.
  Their own `main()` output (two long single-page HTML files) is superseded by the Guide and is no longer committed.
- Captured outputs in `data/captured/` are re-runs, labelled as such on the page. Replace them with output from your
  own Claude Code sessions if you want the pages to show those.
