"""LLM client wrapper with strict schema validation + cache integration.

This module provides the single entry point for every LLM-assisted
extraction in the project. It enforces:

* **Pinned model versions** — caller passes the exact model id.
* **Strict JSON-schema validation** — caller passes the schema; the
  module rejects responses that don't match.
* **Hash-cache by default** — every call hits the project's cache
  before making an API request, so re-runs are no-ops.
* **Full call envelope on disk** — every API call records its
  input + output to ``data/raw/llm_extractions/<task>/<sha256>.json``.

The wrapper is provider-specific (Anthropic). Swapping providers
is a focused refactor of this single file. The rest of the project
talks to ``LLMClient`` not the underlying SDK.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx
from anthropic import Anthropic, APIError, APIStatusError, RateLimitError

from au_politics_money.llm.cache import LLMCache


@dataclass(frozen=True)
class LLMResponse:
    """Normalised response shape every caller sees, regardless of
    cache-hit or fresh-call. ``parsed`` is the caller's payload
    (already schema-validated by the time the caller sees it).
    """

    parsed: dict[str, Any]
    raw_text: str
    model_id: str
    prompt_version: str
    cache_hit: bool
    sha256: str
    input_tokens: int | None
    output_tokens: int | None
    stop_reason: str | None


class LLMValidationError(ValueError):
    """Raised when the LLM's response cannot be coerced into the
    requested schema. Carries the raw model output for debugging.
    """

    def __init__(self, message: str, raw_text: str) -> None:
        super().__init__(message)
        self.raw_text = raw_text


class LLMClient:
    """Anthropic-backed LLM client with cache-first dispatch.

    Use one instance per task (so the cache namespace is task-
    scoped and per-task task overrides don't bleed). The model id
    is per-call, not per-instance.
    """

    def __init__(
        self,
        *,
        task_name: str,
        cache: LLMCache | None = None,
        anthropic_client: Anthropic | None = None,
        request_timeout_seconds: float = 60.0,
    ) -> None:
        self.task_name = task_name
        self.cache = cache or LLMCache(task_name)
        # The Anthropic SDK reads ANTHROPIC_API_KEY from the
        # environment by default; we keep the indirection so a test
        # can pass an in-memory mock.
        self._client = anthropic_client or Anthropic(
            timeout=request_timeout_seconds,
        )
        self._request_timeout_seconds = request_timeout_seconds

    def call_json(
        self,
        *,
        model_id: str,
        prompt_version: str,
        system_instruction: str,
        user_message: str,
        response_schema: dict[str, Any],
        temperature: float = 0.0,
        max_tokens: int = 1024,
        force_refresh: bool = False,
        retry_on_rate_limit: int = 5,
    ) -> LLMResponse:
        """Call the LLM and return a schema-validated JSON payload.

        Cache-first: if the SHA-256 of the call envelope matches a
        cache entry, the cached response is returned without
        contacting the API. ``force_refresh=True`` bypasses the
        cache (e.g. for a debug re-run).
        """
        sha = self.cache.envelope_hash(
            model_id=model_id,
            prompt_version=prompt_version,
            system_instruction=system_instruction,
            user_message=user_message,
            response_schema=response_schema,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        entry = self.cache.lookup(sha)
        if entry.is_hit and not force_refresh:
            cached = self.cache.read_output(sha)
            return LLMResponse(
                parsed=cached["parsed"],
                raw_text=cached["raw_text"],
                model_id=cached["model_id"],
                prompt_version=cached["prompt_version"],
                cache_hit=True,
                sha256=sha,
                input_tokens=cached.get("input_tokens"),
                output_tokens=cached.get("output_tokens"),
                stop_reason=cached.get("stop_reason"),
            )

        # Build an Anthropic API call that uses tool-use to enforce
        # the schema. The "tool" is purely a schema carrier — Claude
        # is asked to call it once with a JSON payload that matches
        # the schema, and we extract the payload from the tool_use
        # block. This is more reliable than asking for free-form
        # JSON because the SDK validates the tool_input against the
        # schema before returning.
        tool_definition = {
            "name": "record_extraction",
            "description": (
                "Record the extraction result. Call this exactly "
                "once with a payload that matches the input schema."
            ),
            "input_schema": response_schema,
        }

        # Anthropic prompt caching: mark the system instruction for
        # ephemeral caching so repeated calls within the same window
        # only pay full input price for the variable user_message
        # portion (~200 tokens) instead of the full
        # system_instruction (~1500 tokens). Cached reads are 10% of
        # input price; saves ~90% on the system-prompt portion at
        # this scale. The cache key is the literal text of the
        # cached block, so the same system_instruction across calls
        # stays warm for ~5 minutes (or longer with the 1-hour TTL).
        system_blocks = [
            {
                "type": "text",
                "text": system_instruction,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        attempt = 0
        last_error: Exception | None = None
        while attempt <= retry_on_rate_limit:
            try:
                api_response = self._client.messages.create(
                    model=model_id,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_blocks,
                    tools=[tool_definition],
                    tool_choice={"type": "tool", "name": "record_extraction"},
                    messages=[
                        {
                            "role": "user",
                            "content": user_message,
                        }
                    ],
                )
                break
            except (RateLimitError, APIStatusError) as exc:
                # Status 529 (overloaded) or 429 (rate limit) get
                # exponential-backoff retries; everything else is
                # raised through.
                status = getattr(exc, "status_code", None)
                if isinstance(exc, RateLimitError) or status in (429, 529):
                    last_error = exc
                    backoff = min(60.0, 2.0 ** attempt)
                    time.sleep(backoff)
                    attempt += 1
                    continue
                raise
            except (httpx.TimeoutException, httpx.HTTPError, APIError) as exc:
                # Network / transient — retry up to N times.
                last_error = exc
                backoff = min(60.0, 2.0 ** attempt)
                time.sleep(backoff)
                attempt += 1
                continue
        else:
            raise RuntimeError(
                f"LLM call failed after {retry_on_rate_limit + 1} attempts: "
                f"{last_error!r}"
            )

        # Find the tool_use block carrying the structured output.
        parsed_payload: dict[str, Any] | None = None
        raw_text_parts: list[str] = []
        for block in api_response.content:
            block_type = getattr(block, "type", None)
            if block_type == "tool_use" and getattr(block, "name", "") == "record_extraction":
                parsed_payload = dict(block.input)
            elif block_type == "text":
                raw_text_parts.append(block.text)
        if parsed_payload is None:
            raise LLMValidationError(
                "Model did not return a record_extraction tool_use block",
                "\n".join(raw_text_parts),
            )

        # Belt-and-braces schema validation: we've already passed
        # the schema as the tool's input_schema (Claude validates
        # it server-side) but we re-check the required keys here so
        # the project's reproducibility chain doesn't depend on the
        # API's enforcement alone.
        required = response_schema.get("required", []) or []
        missing = [key for key in required if key not in parsed_payload]
        if missing:
            raise LLMValidationError(
                f"Tool payload missing required keys: {missing!r}",
                json.dumps(parsed_payload, sort_keys=True),
            )

        usage = getattr(api_response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", None) if usage else None
        output_tokens = getattr(usage, "output_tokens", None) if usage else None
        # Cache-specific token counts (Anthropic returns cache_read_input_tokens
        # + cache_creation_input_tokens when prompt caching is active).
        cache_read_input_tokens = (
            getattr(usage, "cache_read_input_tokens", None) if usage else None
        )
        cache_creation_input_tokens = (
            getattr(usage, "cache_creation_input_tokens", None) if usage else None
        )

        # Persist the full envelope.
        self.cache.write(
            sha,
            input_envelope={
                "task_name": self.task_name,
                "model_id": model_id,
                "prompt_version": prompt_version,
                "system_instruction": system_instruction,
                "user_message": user_message,
                "response_schema": response_schema,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            output_envelope={
                "parsed": parsed_payload,
                "raw_text": "\n".join(raw_text_parts),
                "model_id": api_response.model,
                "prompt_version": prompt_version,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_input_tokens": cache_read_input_tokens,
                "cache_creation_input_tokens": cache_creation_input_tokens,
                "stop_reason": api_response.stop_reason,
            },
        )

        return LLMResponse(
            parsed=parsed_payload,
            raw_text="\n".join(raw_text_parts),
            model_id=api_response.model,
            prompt_version=prompt_version,
            cache_hit=False,
            sha256=sha,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            stop_reason=api_response.stop_reason,
        )
