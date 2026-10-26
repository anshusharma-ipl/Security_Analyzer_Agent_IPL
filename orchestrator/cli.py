"""Command line for the workflow orchestrator.

    python -m orchestrator.cli run    <source_folder> <rules_file> [--out DIR] [--policy JSON]
    python -m orchestrator.cli finish <run_dir>

`run` does steps 1 to 5 and then STOPS: it writes <run_dir>/review_queue.json and waits for a person. Open that
file, set decision (approved, edited or rejected), reviewer and reason on each proposal, then run `finish`.
`finish` does steps 6 and 7 and writes report.json, report.md, decision_log.json and (if anything was approved)
fixes.patch. Nothing is ever applied to the source folder.
Exit code: 0 done or waiting for a person, 1 the run stopped, 2 the review is not complete or not usable yet.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .workflow import DEFAULT_POLICY, RunStopped, StillWaiting, Workflow


def _summary(flow: Workflow) -> int:
    phase = flow.meta.get("phase")
    print(f"run {flow.state['run_id']}: {phase}")
    print(f"  files are in {flow.run_dir}")
    if phase == "waiting_for_review":
        print(f"  waiting for a person: edit {os.path.join(flow.run_dir, 'review_queue.json')}, "
              f"then run:  python -m orchestrator.cli finish {flow.run_dir}")
    if phase == "stopped":
        print(f"  STOPPED: {flow.meta.get('stop_reason')}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orchestrator.cli", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="steps 1 to 5, then wait for a person")
    run.add_argument("source_folder")
    run.add_argument("rules_file")
    run.add_argument("--out", default=None, help="folder for out/<run_id>/ (default: ./out, outside the project)")
    run.add_argument("--policy", default="{}", help="JSON overriding policy values, for example '{\"file_cap\": 50}'")
    fin = sub.add_parser("finish", help="apply the person's decisions, then steps 6 and 7")
    fin.add_argument("run_dir")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    if args.command == "run":
        try:
            policy = json.loads(args.policy)
            unknown = set(policy) - set(DEFAULT_POLICY)
            if not isinstance(policy, dict) or unknown:
                raise ValueError(f"unknown policy keys: {sorted(unknown)}")
            flow = Workflow(out_root=args.out)
            flow.start(args.source_folder, args.rules_file, policy)
        except (ValueError, OSError) as exc:
            print(f"cannot start: {exc}", file=sys.stderr)
            return 2
        return _summary(flow)

    try:
        flow = Workflow.load(args.run_dir)
        flow.finish()
    except StillWaiting as exc:
        print(f"not finished: {exc}", file=sys.stderr)
        return 2
    except (RunStopped, OSError, ValueError, KeyError) as exc:
        print(f"cannot finish: {exc}", file=sys.stderr)
        return 1
    return _summary(flow)


if __name__ == "__main__":
    sys.exit(main())
