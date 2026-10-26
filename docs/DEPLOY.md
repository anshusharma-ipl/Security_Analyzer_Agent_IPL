# Hosting the console

The console is a small Python web server (`ui/server.py`, standard library plus `jsonschema`). It is not a static site: it runs the agents and, to check a fix, **runs the tests of the project you upload**. Hosting it means choosing where that code may run.

## Run it on your own computer (recommended for now)

    pip install jsonschema
    python ui/server.py
    # open http://127.0.0.1:8765

It listens on this computer only and answers only to `localhost`.

## Run it in a container

    docker build -t security-analyzer .
    docker run --rm -p 8765:8765 \
      -e CONSOLE_TOKEN=choose-a-long-random-value \
      -e CONSOLE_ALLOWED_HOSTS=your.host.name \
      security-analyzer

Open `http://localhost:8765/?token=choose-a-long-random-value` once. The token is stored in a cookie and removed from the address.

| Setting | What it does |
| --- | --- |
| `CONSOLE_TOKEN` | Required whenever the server listens on a network address. Every request needs it. |
| `CONSOLE_ALLOWED_HOSTS` | Comma-separated host names the console may answer to (a guard against DNS rebinding). |
| `PORT` | Port to listen on. Default 8765. |
| `AI_MODEL_ENDPOINT`, `AI_MODEL_NAME`, `ANTHROPIC_API_KEY` | Optional. Lets the console use a model (see the Guide). Set them as secrets, not in the image. |

## Risks to accept before putting it on a shared network

- **Remote code execution by design.** Uploaded tests run on the host. Use a container with no secrets, no access to your internal network, a read-only root file system and a CPU and memory limit. Scan only code you trust.
- **One run at a time.** The tools keep a process-wide event list, so a second scan waits. This is a pilot tool, not a multi-user service.
- **Data.** Uploads and run folders are kept under `ui_data/` until you delete them. With a model connected, masked code is sent to that endpoint: use fake data until compliance signs off.
- **No accounts.** The token is a shared secret. Put the console behind your own login (a reverse proxy or your platform's access control) before widening access.

## Publish the site on GitHub Pages

`.github/workflows/pages.yml` builds a static site (the console replay of recorded runs, the Guide, PRD, cost calculator, canvas, test cases and documents) and publishes it on every push to `master`.

1. In the repository, open Settings > Pages and set Source to **GitHub Actions**.
2. Merge `feature/console-model-guide` into `master` (or run the "Publish site" workflow by hand).
3. The site opens at `https://anshusharma-ipl.github.io/Security_Analyzer_Agent_IPL/`.

Pages shows recorded runs only. It cannot run scans, because there is no Python behind it.

## Where not to host it

A static host (GitHub Pages, an artifact page, a file share) can show the Guide and the recorded replay but cannot run scans, because there is no Python to run.
