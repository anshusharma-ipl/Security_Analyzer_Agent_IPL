# Console (ui/)

A local web page for the whole flow: add a project, watch the agents work step by step, approve the fixes that are ready, and download the report and the patch.

    python ui/server.py            # then open http://127.0.0.1:8765      (or double-click start.bat / run start.sh)

## How the page is laid out

- **Left: settings.** (1) The project: drop a folder or a .zip, or choose **Use the demo project** (built in, all six rule types). (2) The model: pick a provider, a model name, paste a key, **Connect**, **Test**. A note says what leaves the computer. **Run scan** is always in reach.
- **Right: the scan.** The **agent flow** adds a step each time something happens (an agent starts, a tool runs, the tests pass, the re-check is clear) and shows what is happening now. The **findings** appear as they are found, one card each, and update in place, so nothing redraws or flickers. A fix that is ready has **Approve this fix**, **Reject** and **Edit**; a sticky bar counts the decisions and has **Finish**. The **What was fixed** screen shows what was fixed (before and after), what still needs you (with what to do), and the downloads.

## Models

OpenAI (GPT), Anthropic (Claude) and Google (Gemini), or an OpenAI- or Anthropic-compatible gateway under **Other**. The request format follows from the provider, so there is nothing to choose. Model names are suggestions; type any name the provider accepts. The key is held in memory only and never saved or shown again. Without a model the built-in agents run: no key, nothing leaves the computer.

With a model connected, the code the agents read is sent to that provider and only to it, with secrets, emails and phone numbers replaced by placeholders first. That masking is automatic and has no setting. There is no consent checkbox. Use fake or non-sensitive code until your security team has approved the provider.

## Behaviour to know about

- **Unclear cause.** By default the console still prepares a local fix when the only objection is "no caller visible", and says so on the proposal. You always approve. (`fix_when_cause_unclear`, see `AGENTS.md` section 5.)
- **Report-only rules.** A hard-coded secret, a weak hash and an old dependency are never patched. Each is shown as a task for you (rotate the key, use a password hash, raise the pin).
- **One console per port.** If port 8765 is taken, the console refuses to start and says what is running there. `/healthz` shows the commit, a code fingerprint, the folder and the process ID, so an old console is easy to spot. `start.bat` opens the browser only for the console it started.

## Other facts

- It runs the real orchestrator (`orchestrator/workflow.py`).
- Downloads: report.html, report.md, report.json, fixes.patch, decision_log.json, state.json, or everything as a .zip. `fixes.patch` is never applied for you: from your project folder run `git apply fixes.patch`.
- Safety: listens on 127.0.0.1 only and refuses other Host headers; zip-slip and symlinks are refused; uploads and run files go to `ui_data/` (git-ignored), never next to the code under scan; golden cases and the demo are copied before a run.
- IMPORTANT: the project's own tests are executed on this computer to verify a fix. Upload only code you trust, until the container from the pilot plan exists.
- Live steps hold names and counts only (an agent, a tool, a file name), never code. `GET /api/jobs/<id>?since=N` returns only the steps after the first N.
- Standard library only (`AGENTS.md` section 8). Test: `python -m unittest tests.test_ui`.
