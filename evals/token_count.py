"""Count tokens with the Claude tokenizer, using the token-counting endpoint. No text is generated.

Used by evals/measure_handoffs.py to replace the 4-characters-per-token proxy with the real count for one model
(claude-sonnet-5-5). It sends only the payloads the agents already exchange in a golden run (fake data), masked first.

Guards, all in code (AGENTS.md section 4 NEVER list, canvas section 13):
  - nothing is sent unless .env sets AI_MODEL_ENDPOINT to the endpoint you approve (the same setting the run record
    uses); with "none" or unset the call is refused before any network access (tools/_containment.check_endpoint);
  - the API key is read from the ANTHROPIC_API_KEY environment variable only. It is never written to a file, a log or
    an error message;
  - text goes through tools/_containment.to_model first (secrets, emails and phone numbers hidden, then re-checked).

Counting a message adds a small framing overhead. It is measured once (a one-character message) and subtracted, so
the figures are the tokens of the text itself, to within a token or two.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools._containment import ContainmentViolation, check_endpoint, to_model  # noqa: E402
from tools._mask import Masker  # noqa: E402

MODEL = "claude-sonnet-5-5"
API_VERSION = "2023-06-01"
PATH = "/v1/messages/count_tokens"
KEY_VARIABLE = "ANTHROPIC_API_KEY"


class CountError(RuntimeError):
    """The count could not be made. The message never contains the API key."""


def approved_endpoint(env_path: str | None = None) -> str:
    """AI_MODEL_ENDPOINT from .env, or "none"."""
    path = env_path or os.path.join(ROOT, ".env")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                key, sep, value = line.strip().partition("=")
                if sep and key.strip() == "AI_MODEL_ENDPOINT":
                    return value.strip()
    return "none"


def _urllib_post(url: str, headers: dict, body: bytes, timeout: int = 60) -> dict:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - endpoint checked by the caller
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise CountError(f"the token-counting call failed with HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise CountError(f"the token-counting call failed ({type(exc).__name__})") from None


class TokenCounter:
    """Counts the tokens of texts for one model. ``post`` is the HTTP call (replaced by a fake in tests)."""

    def __init__(self, model: str = MODEL, endpoint: str | None = None, api_key: str | None = None, post=_urllib_post) -> None:
        self.model, self.post = model, post
        self.approved = approved_endpoint() if endpoint is None else endpoint
        self._key = api_key if api_key is not None else os.environ.get(KEY_VARIABLE, "")
        self.calls = 0
        self.masked = Masker()
        try:
            check_endpoint(self.approved.rstrip("/") + PATH, self.approved)
        except ContainmentViolation as exc:
            raise CountError(f"{exc}. Set AI_MODEL_ENDPOINT in .env (for example https://api.anthropic.com) once you approve it") from None
        if not self._key:
            raise CountError(f"the environment variable {KEY_VARIABLE} is not set")
        self._overhead = self._raw("x") - 1          # one character is one token; the rest is message framing

    def _raw(self, text: str) -> int:
        url = self.approved.rstrip("/") + PATH
        check_endpoint(url, self.approved)            # checked again at the point of the call
        headers = {"x-api-key": self._key, "anthropic-version": API_VERSION, "content-type": "application/json"}
        body = json.dumps({"model": self.model, "messages": [{"role": "user", "content": text}]}).encode("utf-8")
        self.calls += 1
        reply = self.post(url, headers, body)
        if not isinstance(reply, dict) or not isinstance(reply.get("input_tokens"), int):
            raise CountError("the token-counting reply had no input_tokens")
        return reply["input_tokens"]

    def count(self, text: str) -> int:
        """Tokens in ``text`` (masked first, then counted, framing overhead removed)."""
        if not text:
            return 0
        safe = to_model(text, self.masked)
        return max(0, self._raw(safe) - self._overhead)
