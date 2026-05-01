"""SHA-256 hash cache for LLM extractions.

Cache layout (under ``data/raw/llm_extractions/<task>/``):

* ``<sha256>.input.json``  — full request envelope (model, prompt,
  schema, content, parameters). Lets a researcher reconstruct the
  exact API call without re-running the script.
* ``<sha256>.output.json`` — full response (parsed JSON content +
  raw model output + token-usage stats + model metadata).

The cache is content-addressable: the same input → same hash →
same output. Re-running the same script with the same inputs and
the same prompt version is a no-op (cache hit).

The hash includes:
  - model_id (e.g. claude-sonnet-4-6)
  - prompt_version (e.g. entity_industry_classification_v1)
  - system_instruction text
  - user_message text  (which contains the per-call content)
  - response_schema JSON
  - temperature
  - max_tokens

So changing any of these (e.g. updating the prompt to v2) creates
a fresh cache namespace by design — old responses stay on disk for
audit/reproducibility but are not re-used for new prompt versions.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from au_politics_money.config import RAW_DIR


CACHE_BASE_DIR = RAW_DIR / "llm_extractions"


@dataclass(frozen=True)
class CacheEntry:
    sha256: str
    input_path: Path
    output_path: Path

    @property
    def is_hit(self) -> bool:
        return self.input_path.exists() and self.output_path.exists()


class LLMCache:
    """File-system-backed cache keyed by SHA-256 of the full call
    envelope. Reads + writes are atomic from the project layer's
    perspective (one .input.json + one .output.json per hash).
    """

    def __init__(self, task_name: str, *, base_dir: Path | None = None) -> None:
        self.task_name = task_name
        self.task_dir = (base_dir or CACHE_BASE_DIR) / task_name
        self.task_dir.mkdir(parents=True, exist_ok=True)

    def envelope_hash(
        self,
        *,
        model_id: str,
        prompt_version: str,
        system_instruction: str,
        user_message: str,
        response_schema: dict[str, Any] | None,
        temperature: float,
        max_tokens: int,
    ) -> str:
        canonical = json.dumps(
            {
                "model_id": model_id,
                "prompt_version": prompt_version,
                "system_instruction": system_instruction,
                "user_message": user_message,
                "response_schema": response_schema,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def lookup(self, sha256: str) -> CacheEntry:
        return CacheEntry(
            sha256=sha256,
            input_path=self.task_dir / f"{sha256}.input.json",
            output_path=self.task_dir / f"{sha256}.output.json",
        )

    def read_output(self, sha256: str) -> dict[str, Any]:
        path = self.task_dir / f"{sha256}.output.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def write(
        self,
        sha256: str,
        *,
        input_envelope: dict[str, Any],
        output_envelope: dict[str, Any],
    ) -> None:
        input_path = self.task_dir / f"{sha256}.input.json"
        output_path = self.task_dir / f"{sha256}.output.json"
        # Write to .tmp first then rename, so a crash mid-write
        # doesn't leave a partial file the next run treats as a
        # cache hit.
        input_tmp = input_path.with_suffix(".input.json.tmp")
        output_tmp = output_path.with_suffix(".output.json.tmp")
        input_tmp.write_text(
            json.dumps(input_envelope, sort_keys=True, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        output_tmp.write_text(
            json.dumps(output_envelope, sort_keys=True, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        input_tmp.replace(input_path)
        output_tmp.replace(output_path)

    def clear_task(self) -> int:
        """Remove every cache entry for this task. Returns the number
        of files deleted. Use sparingly — the cache is the project's
        reproducibility surface for prior runs.
        """
        count = 0
        for path in self.task_dir.glob("*.json"):
            path.unlink()
            count += 1
        return count
