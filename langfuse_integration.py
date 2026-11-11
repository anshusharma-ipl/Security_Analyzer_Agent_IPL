from __future__ import annotations

import atexit
import os
from contextvars import ContextVar
from typing import Any

try:
    from langfuse import get_client  # type: ignore
except Exception:  # pragma: no cover
    get_client = None  # type: ignore

ACTIVE_TRACE: ContextVar[Any | None] = ContextVar("langfuse_active_trace", default=None)


def _load_env_values(path: str | None = None) -> dict[str, str]:
    values: dict[str, str] = {}
    env_path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.isfile(env_path):
        return values
    with open(env_path, encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def get_env_values() -> dict[str, str]:
    values = dict(os.environ)
    values.update(_load_env_values())
    return values


def get_langfuse_client() -> Any | None:
    if get_client is not None:
        try:
            values = get_env_values()
            if values.get("LANGFUSE_PUBLIC_KEY") and values.get("LANGFUSE_SECRET_KEY"):
                return get_client()
        except Exception:
            pass

    try:
        from langfuse import Langfuse  # type: ignore

        values = get_env_values()
        public_key = values.get("LANGFUSE_PUBLIC_KEY")
        secret_key = values.get("LANGFUSE_SECRET_KEY")
        if not public_key or not secret_key:
            return None
        return Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=values.get("LANGFUSE_BASE_URL") or "https://cloud.langfuse.com",
        )
    except Exception:
        return None


def set_active_trace(trace: Any | None) -> None:
    ACTIVE_TRACE.set(trace)


def get_active_trace() -> Any | None:
    return ACTIVE_TRACE.get()


def flush_langfuse() -> None:
    client = get_langfuse_client()
    if client is None:
        return
    for method_name in ("flush", "shutdown"):
        method = getattr(client, method_name, None)
        if callable(method):
            try:
                method()
            except Exception:
                pass


atexit.register(flush_langfuse)


def start_run_trace(run_id: str, input_data: Any, model: str | None = None, metadata: dict[str, Any] | None = None) -> Any | None:
    client = get_langfuse_client()
    if client is None:
        return None

    base_metadata = {"run_id": run_id, "component": "securityanalyzer"}
    if model:
        base_metadata["model"] = model
    if metadata:
        base_metadata.update(metadata)

    trace = None
    for factory in (
        lambda: client.trace(name=f"securityanalyzer:{run_id}", input=input_data, metadata=base_metadata),
        lambda: client.trace(name=f"securityanalyzer:{run_id}", input=input_data, metadata=base_metadata, user_id=str(run_id)),
    ):
        try:
            trace = factory()
            break
        except TypeError:
            continue
        except Exception:
            break

    if trace is None:
        return None

    set_active_trace(trace)
    return trace


def update_trace(trace: Any | None, *, output: Any | None = None, metadata: dict[str, Any] | None = None) -> None:
    if trace is None:
        return
    try:
        payload: dict[str, Any] = {}
        if output is not None:
            payload["output"] = output
        if metadata:
            payload["metadata"] = metadata
        if payload:
            trace.update(**payload)
    except Exception:
        pass


def _estimate_cost(provider: str, model: str, usage: dict[str, Any]) -> float:
    input_tokens = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
    output_tokens = int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
    provider_name = (provider or "").lower()
    model_name = (model or "").lower()

    if provider_name in {"openai", "azure_openai"}:
        if "gpt-4.1" in model_name or "gpt-4" in model_name:
            return (input_tokens * 0.000005) + (output_tokens * 0.000015)
        if "gpt-4o-mini" in model_name or "mini" in model_name:
            return (input_tokens * 0.00000015) + (output_tokens * 0.0000006)
        return (input_tokens * 0.000002) + (output_tokens * 0.000006)

    if provider_name in {"anthropic", "claude"}:
        if "sonnet" in model_name:
            return (input_tokens * 0.000003) + (output_tokens * 0.000015)
        if "haiku" in model_name:
            return (input_tokens * 0.00000025) + (output_tokens * 0.00000125)
        return (input_tokens * 0.000003) + (output_tokens * 0.000015)

    if provider_name in {"gemini", "google"}:
        if "flash" in model_name:
            return (input_tokens * 0.000000075) + (output_tokens * 0.0000003)
        return (input_tokens * 0.0000015) + (output_tokens * 0.000006)

    return 0.0


def record_model_generation(trace_id: str | None, name: str, model: str, provider: str,
                           request: Any, response: Any,
                           usage: dict[str, Any] | None, metadata: dict[str, Any] | None = None) -> Any | None:
    client = get_langfuse_client()
    if client is None:
        return None

    usage = usage or {}
    payload = {"provider": provider}
    if metadata:
        payload.update(metadata)

    generation_usage = {
        "input": int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0),
        "output": int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0),
    }

    base = {
        "name": name,
        "model": model,
        "input": request,
        "output": response,
        "usage": generation_usage,
        "metadata": payload,
        "cost": _estimate_cost(provider, model, usage),
    }
    if trace_id:
        base["trace_id"] = trace_id

    for factory in (
        lambda: client.generation(**base),
        lambda: client.generation(trace_id=trace_id, name=name, model=model, input=request, output=response,
                                  usage=generation_usage, metadata=payload, cost=_estimate_cost(provider, model, usage)),
    ):
        try:
            return factory()
        except TypeError:
            continue
    return None


__all__ = [
    "ACTIVE_TRACE",
    "flush_langfuse",
    "get_active_trace",
    "get_env_values",
    "get_langfuse_client",
    "record_model_generation",
    "set_active_trace",
    "start_run_trace",
    "update_trace",
]
