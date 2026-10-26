import json, os, sys, glob, csv, re, shutil, tempfile
R=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,R)
from orchestrator.workflow import Workflow
G=os.path.join(R,"golden")
out=tempfile.mkdtemp(prefix="collect-")
idx={r["case_folder"]:r for r in csv.DictReader(open(os.path.join(G,"golden_index.csv"),encoding="utf-8"))}
zipcases={f"case_{i:02d}" for i in range(1,12)}
cases=[]
for name in sorted(d for d in os.listdir(G) if d.startswith("case_")):
    folder=os.path.join(G,name); exp=json.load(open(os.path.join(folder,"expected.json"),encoding="utf-8"))
    files=[]
    for dp,dn,fn in os.walk(folder):
        dn[:]=[d for d in dn if d!="__pycache__"]
        for f in sorted(fn):
            if f=="expected.json": continue
            p=os.path.join(dp,f); files.append({"path":os.path.relpath(p,folder).replace(os.sep,"/"),"text":open(p,encoding="utf-8").read()})
    files.sort(key=lambda x:(x["path"].startswith("tests"),x["path"]))
    # real run through the orchestrator (offline agents), on the real folder; nothing is written to golden
    src=shutil.copytree(folder,os.path.join(out,"src_"+name),ignore=shutil.ignore_patterns("expected.json","__pycache__"))
    fl=Workflow(out_root=os.path.join(out,"o_"+name)); fl.start(src,os.path.join(G,"rules.json"))
    st=fl.state
    run={"phase":fl.meta["phase"],"stop_reason":fl.meta.get("stop_reason"),"outcome":st.get("outcome"),
      "baseline":st.get("baseline_tests"),"findings":[],"handoffs":[{k:h[k] for k in("step","agent","job","finding_id","result","wrote")} for h in st["handoff_log"]],
      "events":[{"event":e["event"],"actor":e["actor"],"detail":e["detail"]} for e in st["audit_log"] if e["event"] in("prompt_injection_attempt","finding_dropped","cap_hit","alert_loop_detected","run_stopped","status_set","invalid_output","agent_failed","fix_failed")],
      "sensitive_hidden":st["sensitive_items_hidden"],"dropped":st.get("dropped_findings",[])}
    status={r["finding_id"]:r for r in st["finding_status"]}
    for c in st.get("candidate_findings",[]):
        inv=next((i for i in st.get("investigations",[]) if i["finding_id"]==c["finding_id"]),None)
        fx=[a for a in st.get("fix_attempts",[]) if a["finding_id"]==c["finding_id"]]
        run["findings"].append({"id":c["finding_id"],"rule":c["rule_id"],"file":c["file"],"line":c["line"],"severity":c["severity"],"confidence":c["confidence"],"evidence":c["evidence"]["quoted_code"],
           "status":status.get(c["finding_id"],{}).get("status"),"reason":status.get(c["finding_id"],{}).get("reason"),
           "investigation":inv,"attempts":[{"attempt":a["attempt"],"patch_diff":a["patch_diff"],"tests":a["tests"],"recheck":a["recheck"],"decision":a["decision"],"residual_risk":a["residual_risk"]} for a in fx]})
    cases.append({"id":name,"in_original_zip":name[:7] in zipcases,"expected":exp,"index":idx.get(name),"files":files,"run":run})
    print(name,run["phase"],[ (f["rule"],f["status"]) for f in run["findings"]])
json.dump(cases,open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"data","cases_data.json"),"w"),indent=1)
shutil.rmtree(out,ignore_errors=True)
