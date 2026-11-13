# Mini demo: a four-finding project for a live demo

A tiny project with four SQL injection findings. Three can be fixed automatically. One needs a person. All data is fake.

| File | What it shows |
| --- | --- |
| `src/customers.py` | a fix with one value |
| `src/invoices.py` | a fix with two values |
| `src/products.py` | a fix where the query runs a line later |
| `src/reports.py` | needs a person: the caller sends part of the SQL itself, so a placeholder cannot replace it |

In the console, drop this folder or `mini_demo.zip` on the Project panel and press **Run scan**.

Run the tests yourself first:

```
python -m unittest discover -s tests
```
