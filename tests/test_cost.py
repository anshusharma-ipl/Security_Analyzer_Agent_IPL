"""Tests for evals/token_count.py and evals/cost_model.py. No network: the HTTP call is replaced by a fake.

    python -m unittest tests.test_cost -v
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "evals"))

import cost_model  # noqa: E402
import token_count  # noqa: E402

KEY = "sk-ant-FAKEKEY1234567890123456789012345"
APPROVED = "https://api.anthropic.com"


class FakeApi:
    """Stands in for the endpoint: 1 token per 4 characters plus 7 tokens of message framing."""

    def __init__(self):
        self.requests = []

    def __call__(self, url, headers, body, timeout=60):
        self.requests.append((url, headers, json.loads(body)))
        text = json.loads(body)["messages"][0]["content"]
        return {"input_tokens": 7 + (len(text) + 3) // 4}


class TestTokenCounter(unittest.TestCase):
    def counter(self, **kw):
        api = FakeApi()
        args = dict(endpoint=APPROVED, api_key=KEY, post=api)
        args.update(kw)
        return token_count.TokenCounter(**args), api

    def test_no_approved_endpoint_means_no_network_call(self):
        api = FakeApi()
        for endpoint in ("none", ""):
            with self.assertRaises(token_count.CountError) as ctx:
                token_count.TokenCounter(endpoint=endpoint, api_key=KEY, post=api)
            self.assertIn("AI_MODEL_ENDPOINT", str(ctx.exception))
        self.assertEqual(api.requests, [])

    def test_no_key_is_refused_without_a_call_and_the_key_never_appears_in_messages(self):
        api = FakeApi()
        with self.assertRaises(token_count.CountError) as ctx:
            token_count.TokenCounter(endpoint=APPROVED, api_key="", post=api)
        self.assertIn("ANTHROPIC_API_KEY", str(ctx.exception))
        self.assertEqual(api.requests, [])

        def failing(url, headers, body, timeout=60):
            raise token_count.CountError("the token-counting call failed with HTTP 401")
        with self.assertRaises(token_count.CountError) as ctx:
            token_count.TokenCounter(endpoint=APPROVED, api_key=KEY, post=failing)
        self.assertNotIn(KEY, str(ctx.exception))

    def test_framing_overhead_is_removed_and_the_request_has_the_right_shape(self):
        counter, api = self.counter()
        self.assertEqual(counter.count("a" * 400), 100)           # 400 characters = 100 tokens, not 107
        self.assertEqual(counter.count(""), 0)
        url, headers, body = api.requests[-1]
        self.assertEqual(url, APPROVED + "/v1/messages/count_tokens")
        self.assertEqual(headers["x-api-key"], KEY)
        self.assertEqual(body["model"], "claude-sonnet-5-5")
        self.assertEqual(body["messages"][0]["role"], "user")

    def test_text_is_masked_before_it_is_sent(self):
        counter, api = self.counter()
        counter.count('API_KEY = "FAKE-KEY-0000-NOT-A-REAL-SECRET" mail asha@example.test')
        sent = api.requests[-1][2]["messages"][0]["content"]
        self.assertNotIn("FAKE-KEY-0000-NOT-A-REAL-SECRET", sent)
        self.assertNotIn("asha@example.test", sent)

    def test_only_the_approved_host_is_contacted(self):
        counter, api = self.counter(endpoint="https://api.anthropic.com/")
        counter.count("hello")
        self.assertTrue(all(url.startswith("https://api.anthropic.com/v1/") for url, _h, _b in api.requests))


MEASURED = {"model": "claude-sonnet-5-5", "token_source": "counted with claude-sonnet-5-5",
            "summary": {"scans": 11, "findings_per_scan": 1.0, "handoffs_per_scan": {"mean": 4.0, "min": 1, "max": 6},
                        "per_agent": {"auditor": {"handoffs": 1.5, "tool_calls": 3, "in_tokens": 3000, "out_tokens": 500},
                                      "investigator": {"handoffs": 1.0, "tool_calls": 1, "in_tokens": 1000, "out_tokens": 100},
                                      "fixer_validator": {"handoffs": 1.5, "tool_calls": 2, "in_tokens": 2000, "out_tokens": 400}}}}
PRICING = {**cost_model.TEMPLATE, "price_input_per_million": 3.0, "price_output_per_million": 15.0, "price_currency": "USD",
           "engineer_hourly_rate": 50.0, "rate_currency": "USD", "engineer_hours_per_scan_today": 2.0}


class TestCostModel(unittest.TestCase):
    def test_the_arithmetic_with_the_x3_overhead_at_three_volumes(self):
        scan = cost_model.per_scan(MEASURED)
        self.assertEqual((scan["in"], scan["out"]), (6000, 1000))
        result = cost_model.costs(scan, PRICING)
        base = (6000 * 3.0 + 1000 * 15.0) / 1_000_000                  # 0.033 per scan
        self.assertAlmostEqual(result["base_per_scan"], base)
        self.assertAlmostEqual(result["per_scan_with_overhead"], base * 3)
        rows = {r["scans_per_day"]: r for r in result["rows"]}
        self.assertEqual(sorted(rows), [5, 20, 100])
        self.assertAlmostEqual(rows[20]["model_cost"], base * 3 * 20 * 30)
        self.assertAlmostEqual(rows[20]["today_cost"], 2.0 * 50.0 * 20 * 30)
        self.assertAlmostEqual(rows[100]["model_cost"] / rows[5]["model_cost"], 20)      # linear in volume

    def test_nothing_is_invented_when_an_input_is_missing(self):
        blank = {**PRICING, "price_input_per_million": None, "engineer_hourly_rate": None}
        self.assertIsNone(cost_model.costs(cost_model.per_scan(MEASURED), blank))
        text, missing = cost_model.build(MEASURED, blank)
        self.assertEqual(len(missing), 2)
        self.assertIn("Not computed", text)
        self.assertIn("## 4. Still unmeasured", text)
        self.assertNotIn("Model cost per month (", text)

    def test_two_currencies_need_an_exchange_rate(self):
        mixed = {**PRICING, "rate_currency": "INR"}
        self.assertTrue(any("exchange rate" in m for m in cost_model.missing_inputs(mixed)))
        ok = {**mixed, "fx_rate_rate_currency_per_price_currency": 83.0}
        self.assertEqual(cost_model.missing_inputs(ok), [])
        rows = cost_model.costs(cost_model.per_scan(MEASURED), ok)["rows"]
        self.assertAlmostEqual(rows[0]["model_cost_in_rate_currency"], rows[0]["model_cost"] * 83.0)

    def test_the_document_says_what_is_unmeasured_and_never_claims_time_saved(self):
        text, missing = cost_model.build(MEASURED, PRICING)
        self.assertEqual(missing, [])
        self.assertIn("Still unmeasured", text)
        self.assertIn("No saving in engineer time is claimed", text)
        self.assertIn("x3", text)


if __name__ == "__main__":
    unittest.main()
