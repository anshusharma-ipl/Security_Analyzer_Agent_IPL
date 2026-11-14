# Mini demo: two findings for a live demo

A tiny project with two SQL injection findings. One can be fixed automatically. One needs a person. All data is fake.

| File | What it shows |
| --- | --- |
| `src/customers.py` | gets a fix: the value goes in through a placeholder |
| `src/reports.py` | needs a person: the caller sends part of the SQL itself, so a placeholder cannot replace it |

In the console, drop this folder or `mini_demo.zip` on the Project panel and press **Run scan**.

Run the tests yourself first:

```
python -m unittest discover -s tests
```
