"""Hide secrets, emails and phone numbers before text leaves a tool.

AGENTS.md: "replace secrets, emails and phone numbers with placeholders before any model
call". Tool results feed the agents, so the tools hide these values themselves.
Placeholders: <SECRET_n>, <EMAIL_n>, <PHONE_n>. ``Masker.hidden`` counts replacements.
"""
from __future__ import annotations

import re

EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<![\w.])\+\d{1,3}[-\s]?\d[\d\-\s]{6,}\d|(?<![\w.])\d{3}[-.\s]\d{3}[-.\s]\d{4}(?!\d)")

# A name that suggests a credential, assigned a quoted literal of 8+ characters.
_SECRET_ASSIGN = re.compile(
    r"""(?ix)
    (?:api[_-]?key|secret|passw(?:or)?d|pwd|token|private[_-]?key|access[_-]?key|auth[_-]?key)
    \w*["']?\s*[:=]\s*[rbuRBU]{0,2}(?P<q>["'])(?P<value>(?:(?!(?P=q))\S){8,})(?P=q)""")
# Well-known credential shapes.
_SECRET_SHAPES = [re.compile(p) for p in (
    r"AKIA[0-9A-Z]{16}",
    r"gh[pousr]_[A-Za-z0-9]{36,}",
    r"sk-[A-Za-z0-9]{20,}",
    r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----",
)]
_PLACEHOLDER_VALUES = {"changeme", "change-me", "change_me", "your-api-key", "your_api_key", "xxxxxxxx", "password"}


def secret_spans(line: str) -> list[tuple[int, int]]:
    """(start, end) spans of secret values on one line. Empty when the line holds none."""
    spans = []
    for m in _SECRET_ASSIGN.finditer(line):
        value = m.group("value")
        lowered = value.lower()
        if lowered in _PLACEHOLDER_VALUES or value.startswith(("<", "{", "${", "%(")):
            continue
        spans.append(m.span("value"))
    for pattern in _SECRET_SHAPES:
        spans += [m.span() for m in pattern.finditer(line)]
    return spans


class Masker:
    def __init__(self) -> None:
        self.counts = {"SECRET": 0, "EMAIL": 0, "PHONE": 0}

    @property
    def hidden(self) -> int:
        return sum(self.counts.values())

    def _tag(self, kind: str) -> str:
        self.counts[kind] += 1
        return f"<{kind}_{self.counts[kind]}>"

    def line(self, text: str) -> str:
        """Hide secrets, then emails and phone numbers, in one piece of text."""
        spans = sorted(set(secret_spans(text)))
        merged: list[list[int]] = []
        for start, end in spans:  # overlapping spans become one secret
            if merged and start < merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        for start, end in reversed(merged):
            text = text[:start] + self._tag("SECRET") + text[end:]
        # SECRET tags were numbered right-to-left; renumber left-to-right for readability.
        text = self._renumber(text)
        text = EMAIL.sub(lambda _m: self._tag("EMAIL"), text)
        return PHONE.sub(lambda _m: self._tag("PHONE"), text)

    @staticmethod
    def _renumber(text: str) -> str:
        counter = iter(range(1, 10_000))
        return re.sub(r"<SECRET_\d+>", lambda _m: f"<SECRET_{next(counter)}>", text)

    def text(self, text: str) -> str:
        """Same as line(), for multi-line text such as test output."""
        return "\n".join(self.line(part) for part in text.splitlines())
