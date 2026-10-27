# Demo shop: sample input for the Security Analyzer Agent

A small sample e-commerce project with a deliberate mix of security issues, covering **all six rule types**, not only SQL injection. All data is fake. In the console choose **Use the demo project**, or upload this folder or `shop_demo.zip`.

Run the tests yourself first:

```
python -m unittest discover -s tests
```

13 findings: 6 SQL injection, 2 command injection, 2 path traversal, 1 hard-coded secret, 1 weak hash, 1 old dependency. Four files are **safe look-alikes** that must produce no finding.

---

## What to expect from the agent

The table shows what happens **without a model** (the built-in agents), checked by running this project with the console's settings. A model can attempt the fixes marked "a model can try".

| File | Issue | Without a model |
|---|---|---|
| `src/users.py` | SQL injection, f-string, used by `service.py` | **Fix ready**: a `?` placeholder. You approve |
| `src/products.py` | SQL injection, f-string, called from `views.py` | **Fix ready** |
| `src/lookup.py` | SQL injection plus a hostile comment aimed at an AI | **Fix ready**; the comment is ignored and logged |
| `src/customers.py` + `src/config.py` | SQL injection plus a hard-coded key | Injection: **fix ready**. Key: needs you (rotate it); it is masked before any model sees it |
| `src/service.py` (from `views.py`, runs through `db.py`) | SQL injection across files | Cause traced across the files; **no fix without a model** (a model can try: `db.run` already accepts parameters) |
| `src/reports.py` | Raw SQL condition sent by the client | **Needs you**: a redesign, not a patch |
| `src/netcheck.py` | Command injection, `shell=True` | **Fix ready**: a command list with no shell |
| `src/archive.py` | Command injection through `os.system` | **Needs you** without a model (a model can try) |
| `src/files.py` | Path traversal | **Fix ready**: resolve the path and refuse anything outside the folder |
| `src/uploads.py` | Path traversal on a file upload | **Fix ready**: the same check |
| `src/accounts.py` | Weak hash (MD5) for passwords | **Needs you**: the right fix needs a password-hashing library |
| `requirements.txt` | `requests==2.19.0`, below 2.31.0 | **Needs you**: the agent never changes dependencies; raise the pin and run your tests |
| `src/orders.py` | Safe: the f-string is only a log line | Nothing reported |
| `src/safe_lookup.py`, `src/safe_files.py`, `src/safe_run.py` | Safe versions of the three fixes | Nothing reported |
| `src/greeting.py`, `src/helpers.py`, `src/db.py`, `src/views.py` | Safe helpers and a dispatcher | Nothing reported |

**Why some findings still need a person.** A fix is prepared only when it is small, local and passes the project's tests and an independent re-check. The fix needs a redesign (`reports.py`), it spans several files or needs something the built-in fixer lacks (`service.py`, `archive.py`), or the rule is report-only (secret, weak hash, dependency). Each of these shows as a task for you, with what to do.

After the agent finishes:
- Review the findings in the console and **approve** the fixes you are happy with
- The approved patches are written to `fixes.patch` (download it from the "What was fixed" screen)
- Apply them to your source with `git apply fixes.patch`
- Re-run the tests to confirm everything still passes

---

## File map

```
src/
  accounts.py    weak hash (MD5)                              (WEAKHASH: needs a person)
  archive.py     command injection through os.system          (CMDI: a model can fix)
  config.py      hard-coded API key                           (SECRET: needs a person)
  customers.py   SQL injection, uses config.API_KEY           (SQLI fix; key masked)
  db.py          query helper; supports parameterized calls   (safe)
  files.py       path traversal                               (PATH fix)
  greeting.py    purely safe helper                           (no finding)
  helpers.py     safe price and pagination utilities          (no finding)
  lookup.py      SQL injection plus a hostile comment         (SQLI fix, comment ignored)
  netcheck.py    command injection, shell=True                (CMDI fix)
  orders.py      safe, already parameterized                  (no finding)
  products.py    SQL injection, called from views             (SQLI fix)
  reports.py     raw SQL condition from the client            (needs a person: redesign)
  safe_files.py, safe_lookup.py, safe_run.py                  (safe look-alikes, no finding)
  service.py     SQL injection, called from views             (a model can fix; db.run takes params)
  uploads.py     path traversal on a file upload              (PATH fix)
  users.py       SQL injection, used by service               (SQLI fix)
  views.py       HTTP dispatcher                              (no finding itself)

tests/           one test file per src module
requirements.txt requests==2.19.0 (outdated: needs a person)
```

Case 08 (no tests) needs a project with no tests, so it is a separate zip: `no_tests_demo.zip`. Expected: the finding is reported and handed to a person, because a fix cannot be verified without tests.
