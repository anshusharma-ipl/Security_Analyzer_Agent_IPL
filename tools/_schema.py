"""Schema loader and validation helpers.

Each tool validates its ARGUMENTS before doing any work (``validate_args``) and the full
call envelope {tool, arguments, response} before returning (``validate_envelope``). Both
raise ``SchemaError`` so a tool can turn the problem into a clear error message.
"""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"
_schemas: dict[str, dict] = {}
_registry: Registry | None = None


def _load() -> None:
    global _registry
    if _registry is not None:
        return
    for p in sorted(_SCHEMA_DIR.glob("*.schema.json")):
        _schemas[p.name.removesuffix(".schema.json")] = json.loads(p.read_text(encoding="utf-8"))
    _registry = Registry().with_resources([(s["$id"], Resource.from_contents(s)) for s in _schemas.values()])


class SchemaError(ValueError):
    """A payload does not match its schema."""

    def __init__(self, location: str, message: str) -> None:
        self.location = location
        self.message = message
        super().__init__(f"{location}: {message}")


def _check(validator: Draft202012Validator, payload: object) -> None:
    errors = sorted(validator.iter_errors(payload), key=lambda e: [str(p) for p in e.absolute_path])
    if errors:
        e = errors[0]
        location = "/".join(str(p) for p in e.absolute_path) or "(root)"
        message = " ".join(e.message.split())
        raise SchemaError(location, message if len(message) <= 200 else message[:197] + "...")


def validate_args(tool_name: str, arguments: object) -> None:
    """Check ``arguments`` against the arguments part of schemas/tool_<tool_name>.schema.json."""
    _load()
    schema = _schemas[f"tool_{tool_name}"]
    wrapper = {"$schema": schema["$schema"], "$defs": schema.get("$defs", {}), **schema["properties"]["arguments"]}
    _check(Draft202012Validator(wrapper, registry=_registry), arguments)


def validate_envelope(tool_name: str, envelope: object) -> None:
    """Check the full {tool, arguments, response} envelope against the tool's schema."""
    _load()
    _check(Draft202012Validator(_schemas[f"tool_{tool_name}"], registry=_registry), envelope)


def ok(tool_name: str, arguments: dict, result: dict) -> dict:
    envelope = {"tool": tool_name, "arguments": arguments, "response": {"ok": True, "result": result}}
    validate_envelope(tool_name, envelope)
    return envelope


def fail(tool_name: str, arguments: dict, code: str, message: str, handling: str, **extra) -> dict:
    error = {"code": code, "message": message, "handling": handling, **extra}
    envelope = {"tool": tool_name, "arguments": arguments, "response": {"ok": False, "error": error}}
    validate_envelope(tool_name, envelope)
    return envelope


def validate_document(schema_name: str, document: object) -> None:
    """Check a non-tool document (for example rules.json) against schemas/<schema_name>.schema.json."""
    _load()
    _check(Draft202012Validator(_schemas[schema_name], registry=_registry), document)
