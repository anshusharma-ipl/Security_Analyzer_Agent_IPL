"""Demo helper: show a run's handoff trace and prove the original folder is unchanged.

    python evals/show_trace.py out/demo/run-001

Prints (1) the handoff trace: every orchestrator-to-agent step, who wrote which state fields, the result; (2) the
decision log lines that matter (statuses, injection notes, approvals, the originals check); (3) an INDEPENDENT proof:
the original folder is hashed again right now and compared with the hashes taken before the run started (kept in
run_meta.json), file by file. Reads only.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.orchestrator_helpers import verify_originals  # noqa: E402

if len(sys.argv) != 2:
    sys.exit(__doc__)
run_dir = sys.argv[1]
read = lambda name: json.load(open(os.path.join(run_dir, name), encoding="utf-8"))  # noqa: E731
state, meta = read("state.json"), read("run_meta.json")
sys.stdout.reconfigure(encoding="utf-8")

print(f"RUN {state['run_id']}  phase: {meta['phase']}  source: {state['input']['source_folder']}")
print(f"rules file version: {state['rules_file_version'][:23]}...   model: {state['ai_model']['name']}")

print("\n1. HANDOFF TRACE (every handoff goes through the orchestrator; agents never call each other)")
print(f"   {'step':<5}{'agent':<17}{'job':<16}{'finding':<9}{'result':<9}wrote")
for h in state["handoff_log"]:
    print(f"   {h['step']:<5}{h['agent']:<17}{h['job']:<16}{(h['finding_id'] or '-'):<9}{h['result']:<9}{', '.join(h['wrote'])}")
print(f"   steps {state['counters']['steps']} (cap {state['input']['policy']['step_cap']}), "
      f"AI calls {state['counters']['ai_calls']}, tokens {state['counters']['tokens']}")

print("\n2. DECISIONS")
shown = ("findings_ranked", "nothing_found", "prompt_injection_attempt", "status_set", "fix_approved", "fix_edited",
         "fix_rejected", "originals_verified", "originals_changed", "run_stopped")
for e in state["audit_log"]:
    if e["event"] in shown:
        print(f"   #{e['seq']:<3}{e['actor']:<14}{e['event']:<26}{e.get('finding_id', ''):<6}{e['detail'][:90]}")
for row in state["finding_status"]:
    print(f"   STATUS {row['finding_id']}: {row['status']}" + (f" ({row['reason']})" if row["reason"] else ""))

print("\n3. ORIGINALS UNCHANGED (independent check, done now)")
baseline = meta.get("originals_hash")
if not baseline:
    print("   no baseline hashes in run_meta.json")
else:
    check = verify_originals(state["input"]["source_folder"], baseline)
    print(f"   {len(baseline)} original files were fingerprinted (SHA-256) before the run started")
    print(f"   hashed again just now: changed {check['changed']}, added {check['added']}, removed {check['removed']}")
    print(f"   -> {'UNCHANGED' if check['unchanged'] else 'CHANGED: stop rule would fire'}")
    print(f"   run recorded originals_unchanged = {state['originals_unchanged']}")
