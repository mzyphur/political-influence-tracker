"""LLM-assisted extraction module for the project's hybrid pipeline.

This sub-package wraps Anthropic's Claude API behind a thin
provider-agnostic abstraction (`LLMClient`) plus a SHA-256 hash
cache (`LLMCache`) that makes every extraction reproducible at the
project layer even though the underlying model isn't.

Architectural promises:

* **Determinism at the project layer.** Every LLM input is hashed
  (SHA-256 of the canonicalised prompt + system instruction +
  schema + content). Hash → cached response. Re-running with the
  same input returns the cached output verbatim, so a researcher
  who clones the repo + downloads the cached responses gets
  byte-for-byte identical extraction results without an API key.
* **Pinned model versions.** Every call records the exact model ID
  (e.g. ``claude-sonnet-4-6``) and any pinned snapshot date. The
  cache key includes the model ID, so swapping models invalidates
  the cache by design.
* **Strict schema validation.** Every LLM response is validated
  against a JSON schema before it's accepted; malformed responses
  are rejected with a structured error rather than silently
  reshaped.
* **Full call envelope on disk.** Every LLM call's input, output,
  model, and parameters land at
  ``data/raw/llm_extractions/<task>/<sha256>.json`` so the
  extraction is reproducible without re-invoking the API.
* **No money-flow extraction.** The byte-identical-totals
  invariant remains the top rule. LLM-extracted rows are tagged
  with ``extraction_method='llm_<task>_v<n>'`` and never feed
  direct-money totals.
* **Public-facing prompts.** Every prompt is versioned in
  ``prompts/<task>/v<N>.md`` and committed to the public mirror.
  Anyone can audit, fork, or improve.
"""

from au_politics_money.llm.client import LLMClient, LLMResponse
from au_politics_money.llm.cache import LLMCache

__all__ = ("LLMClient", "LLMResponse", "LLMCache")
