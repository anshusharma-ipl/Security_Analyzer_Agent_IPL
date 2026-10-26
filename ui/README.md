# Console (ui/)

A local web page for the whole flow: pick or upload a project, watch the agents run, approve / edit / reject each
proposed fix, download the report.

    python ui/server.py            # then open http://127.0.0.1:8765

- Input: a golden case, a .zip of a Python project, or a picked folder. Optional: your own rules.json, file_cap, max_retries.
- It runs the real orchestrator (orchestrator/workflow.py). The three agents are still the offline stand-ins until a model
  endpoint is approved, so only the f-string SQL pattern gets an automatic patch.
- Downloads: report.html, report.md, report.json, fixes.patch, decision_log.json, state.json, or everything as a .zip.
  fixes.patch is never applied for you: from your project folder run `git apply fixes.patch`.
- Safety: listens on 127.0.0.1 only and refuses other Host headers; zip-slip and symlinks are refused; uploads and run
  files go to ui_data/ (git-ignored), never next to the code under scan; golden cases are copied before a run.
- IMPORTANT: the project's own tests are executed on this computer to verify a fix. Upload only code you trust, until
  the container from the pilot plan exists.
- Standard library only (AGENTS.md section 8). Test: `python -m unittest tests.test_ui`.
