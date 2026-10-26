"""Demo helper: the presenter plays the person and approves every waiting proposal in a run's review_queue.json.

    python evals/demo_approve.py out/demo/run-001 "Your Name"

This is the same edit a person makes by hand in review_queue.json (decision, reviewer, reason), done in one command so
the demo stays short. Nothing is applied to any original folder; approval only lets `finish` write fixes.patch.
"""
import json
import os
import sys

if len(sys.argv) != 3:
    sys.exit(__doc__)
run_dir, reviewer = sys.argv[1], sys.argv[2]
path = os.path.join(run_dir, "review_queue.json")
with open(path, encoding="utf-8") as handle:
    queue = json.load(handle)
if not queue["proposals"]:
    sys.exit("nothing is waiting for a decision in this run")
for proposal in queue["proposals"]:
    proposal.update(decision="approved", reviewer=reviewer, reason="demo approval by the presenter")
    print(f"approved {proposal['finding_id']} ({proposal['rule_id']} {proposal['file']}:{proposal['line']}) as {reviewer}")
with open(path, "w", encoding="utf-8", newline="\n") as handle:
    json.dump(queue, handle, indent=2)
print(f"now run: python -m orchestrator.cli finish {run_dir}")
