#!/usr/bin/env python3
"""Inter-rater reliability (IRR) statistics for LLM-extracted classifications.

This is the project's scientific-validation backbone for every
LLM-assisted extraction stage. The output is a JSON + Markdown
report under `data/audit/llm_inter_rater_reliability/<task>/<ts>.{json,md}`
that quantifies agreement between:

  * Two model versions of the same task (e.g. Haiku v1 vs Sonnet v2
    on the same 200 AusTender contracts).
  * The LLM and a human reviewer (when the reviewer adjudication
    JSONL is provided via `--reviewer-jsonl`).
  * The LLM and a deterministic cross-validator (e.g. UNSPSC code
    family vs LLM-emitted sector — used as a side-channel sanity
    check, not ground truth).

Statistics computed:

  * **Observed agreement (po)** — fraction of items where both
    raters agree exactly. Per-attribute (sector, procurement_class,
    confidence) and overall.
  * **Expected agreement by chance (pe)** — under marginal-
    independence null. Computed from each rater's distribution.
  * **Cohen's kappa (κ)** = (po - pe) / (1 - pe). Values:
    ≥ 0.81 almost perfect, 0.61-0.80 substantial, 0.41-0.60
    moderate, 0.21-0.40 fair, ≤ 0.20 slight.
  * **Per-class Cohen's kappa** for fine-grained inspection.
  * **Jaccard similarity** for the array-valued attribute
    `policy_topics` (multi-label classification). Reported
    per-pair and averaged.
  * **F1 (macro + micro)** for `policy_topics` treating the
    multi-label problem as 24 binary classifiers.

Methodology pinned (replicable across runs):

  * Sample is the FULL overlap set when both raters have classified
    the same items (no cherry-picking). For the AusTender v1-vs-v2
    comparison, that's the first 200 contracts which both pilots
    covered.
  * No bootstrap CIs at this scale (200 items is too small for
    stable bootstrap CIs at the per-class level); we report point
    estimates + the count of items each estimate is based on. Future
    work: at scale (>5,000 items per stage), add bootstrap 95% CIs.
  * IRR is recomputed every time a prompt version changes, every
    time the model changes, and every time the cache is rebuilt.

Operational shape:

    cd <project root>
    backend/.venv/bin/python scripts/compute_llm_inter_rater_reliability.py \\
        --task austender_contract_topic_tag \\
        --rater-a-jsonl data/processed/llm_austender_topic_tags/<v1>.jsonl \\
        --rater-a-label "Haiku 4.5 v1" \\
        --rater-b-jsonl data/processed/llm_austender_topic_tags/<v2>.jsonl \\
        --rater-b-label "Sonnet 4.6 v2" \\
        --join-key contract_id

The joinable-key per record varies by task:
  * austender_contract_topic_tag: `contract_id`
  * register_of_interests_extraction: `(source_id, section_number)`
    (since each section can produce 0..N items, IRR for ROI works
    on the SECTION level — agreement = both produced same item
    count + same set of (item_type, counterparty_name) tuples).
  * entity_industry_classification: `entity_id`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# -----------------------------------------------------------------
# Statistics primitives.
# -----------------------------------------------------------------


def cohens_kappa_nominal(rater_a: list[Any], rater_b: list[Any]) -> dict[str, float | int]:
    """Cohen's kappa for nominal categories. Returns observed
    agreement, expected agreement, kappa, n.

    Both rater lists must have the same length; rater_a[i] is
    paired with rater_b[i].
    """
    assert len(rater_a) == len(rater_b), (
        "rater_a and rater_b must be same length"
    )
    n = len(rater_a)
    if n == 0:
        return {"observed_agreement": 0.0, "expected_agreement": 0.0, "kappa": 0.0, "n": 0}

    agree = sum(1 for a, b in zip(rater_a, rater_b, strict=True) if a == b)
    po = agree / n

    counts_a = Counter(rater_a)
    counts_b = Counter(rater_b)
    categories = set(counts_a.keys()) | set(counts_b.keys())
    pe = sum(
        (counts_a.get(c, 0) / n) * (counts_b.get(c, 0) / n)
        for c in categories
    )

    if pe >= 1.0:
        # All items in one category — kappa undefined; treat as
        # perfect agreement if po == 1, otherwise as 0 (degenerate).
        kappa = 1.0 if po == 1.0 else 0.0
    else:
        kappa = (po - pe) / (1.0 - pe)

    return {
        "observed_agreement": round(po, 4),
        "expected_agreement": round(pe, 4),
        "kappa": round(kappa, 4),
        "n": n,
    }


def per_class_kappa(
    rater_a: list[Any], rater_b: list[Any]
) -> dict[str, dict[str, float | int]]:
    """Per-category one-vs-rest Cohen's kappa. Useful for spotting
    classes where the two raters disagree most.
    """
    n = len(rater_a)
    if n == 0:
        return {}
    categories = sorted(set(rater_a) | set(rater_b))
    out: dict[str, dict[str, float | int]] = {}
    for c in categories:
        bin_a = [1 if a == c else 0 for a in rater_a]
        bin_b = [1 if b == c else 0 for b in rater_b]
        out[c] = cohens_kappa_nominal(bin_a, bin_b)
        out[c]["count_rater_a"] = sum(bin_a)
        out[c]["count_rater_b"] = sum(bin_b)
    return out


def jaccard_similarity(set_a: set[Any], set_b: set[Any]) -> float:
    if not set_a and not set_b:
        return 1.0  # both empty — perfect agreement
    union = set_a | set_b
    if not union:
        return 1.0
    intersection = set_a & set_b
    return len(intersection) / len(union)


def multilabel_metrics(
    rater_a: list[set[Any]], rater_b: list[set[Any]]
) -> dict[str, float | int]:
    """Multi-label classification metrics: Jaccard (per pair, mean),
    per-label Cohen's kappa averaged (macro), micro-F1.

    Each item's policy_topics is a set; both raters' sets are
    compared.
    """
    n = len(rater_a)
    if n == 0:
        return {"n": 0}
    jaccards = [
        jaccard_similarity(a, b) for a, b in zip(rater_a, rater_b, strict=True)
    ]
    mean_jaccard = sum(jaccards) / n

    # Build per-label binary vectors; compute kappa per label.
    all_labels = sorted(set().union(*rater_a, *rater_b))
    label_kappas: dict[str, dict[str, float | int]] = {}
    label_f1s: list[float] = []
    micro_tp = 0
    micro_fp = 0
    micro_fn = 0
    for label in all_labels:
        bin_a = [1 if label in s else 0 for s in rater_a]
        bin_b = [1 if label in s else 0 for s in rater_b]
        kappa_stats = cohens_kappa_nominal(bin_a, bin_b)
        label_kappas[label] = kappa_stats
        # F1
        tp = sum(1 for x, y in zip(bin_a, bin_b, strict=True) if x and y)
        fp = sum(1 for x, y in zip(bin_a, bin_b, strict=True) if (not x) and y)
        fn = sum(1 for x, y in zip(bin_a, bin_b, strict=True) if x and (not y))
        micro_tp += tp
        micro_fp += fp
        micro_fn += fn
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        if precision + recall > 0:
            label_f1s.append(2 * precision * recall / (precision + recall))
        else:
            label_f1s.append(0.0)

    macro_f1 = sum(label_f1s) / len(label_f1s) if label_f1s else 0.0
    micro_precision = (
        micro_tp / (micro_tp + micro_fp) if (micro_tp + micro_fp) > 0 else 0.0
    )
    micro_recall = (
        micro_tp / (micro_tp + micro_fn) if (micro_tp + micro_fn) > 0 else 0.0
    )
    micro_f1 = (
        2 * micro_precision * micro_recall / (micro_precision + micro_recall)
        if (micro_precision + micro_recall) > 0
        else 0.0
    )

    macro_kappa = sum(
        v["kappa"] for v in label_kappas.values()
    ) / len(label_kappas) if label_kappas else 0.0

    return {
        "n": n,
        "mean_jaccard": round(mean_jaccard, 4),
        "median_jaccard": round(sorted(jaccards)[n // 2], 4) if n > 0 else 0.0,
        "macro_kappa": round(macro_kappa, 4),
        "macro_f1": round(macro_f1, 4),
        "micro_f1": round(micro_f1, 4),
        "per_label_kappa": label_kappas,
    }


def kappa_interpretation(kappa: float) -> str:
    """Landis & Koch (1977) interpretation."""
    if kappa < 0:
        return "poor (worse than chance)"
    if kappa <= 0.20:
        return "slight"
    if kappa <= 0.40:
        return "fair"
    if kappa <= 0.60:
        return "moderate"
    if kappa <= 0.80:
        return "substantial"
    return "almost perfect"


# -----------------------------------------------------------------
# Per-task IRR drivers.
# -----------------------------------------------------------------


def irr_austender_contract_topic_tag(
    a_records: list[dict[str, Any]],
    b_records: list[dict[str, Any]],
    a_label: str,
    b_label: str,
) -> dict[str, Any]:
    """IRR for Stage 3 contract tagging."""
    a_idx = {r["contract_id"]: r for r in a_records if "sector" in r}
    b_idx = {r["contract_id"]: r for r in b_records if "sector" in r}
    common_ids = sorted(set(a_idx.keys()) & set(b_idx.keys()))
    if not common_ids:
        return {"error": "No overlapping contract_ids between the two raters"}

    a = [a_idx[i] for i in common_ids]
    b = [b_idx[i] for i in common_ids]

    sector_a = [r["sector"] for r in a]
    sector_b = [r["sector"] for r in b]
    proc_a = [r["procurement_class"] for r in a]
    proc_b = [r["procurement_class"] for r in b]
    conf_a = [r["confidence"] for r in a]
    conf_b = [r["confidence"] for r in b]
    topics_a = [set(r["policy_topics"]) for r in a]
    topics_b = [set(r["policy_topics"]) for r in b]

    sector_kappa = cohens_kappa_nominal(sector_a, sector_b)
    proc_kappa = cohens_kappa_nominal(proc_a, proc_b)
    conf_kappa = cohens_kappa_nominal(conf_a, conf_b)
    topics_metrics = multilabel_metrics(topics_a, topics_b)
    sector_per_class = per_class_kappa(sector_a, sector_b)

    return {
        "task": "austender_contract_topic_tag",
        "rater_a": a_label,
        "rater_b": b_label,
        "common_n": len(common_ids),
        "sector": {
            **sector_kappa,
            "interpretation": kappa_interpretation(sector_kappa["kappa"]),
        },
        "procurement_class": {
            **proc_kappa,
            "interpretation": kappa_interpretation(proc_kappa["kappa"]),
        },
        "confidence": {
            **conf_kappa,
            "interpretation": kappa_interpretation(conf_kappa["kappa"]),
        },
        "policy_topics": topics_metrics,
        "sector_per_class_kappa": sector_per_class,
    }


def irr_register_of_interests(
    a_records: list[dict[str, Any]],
    b_records: list[dict[str, Any]],
    a_label: str,
    b_label: str,
) -> dict[str, Any]:
    """IRR for Stage 2 ROI extraction. Section-level: agreement on
    item count + set of (item_type, counterparty_name) tuples per
    section."""
    a_idx = {(r["source_id"], str(r["section_number"])): r for r in a_records}
    b_idx = {(r["source_id"], str(r["section_number"])): r for r in b_records}
    common = sorted(set(a_idx.keys()) & set(b_idx.keys()))
    if not common:
        return {"error": "No overlapping (source_id, section_number) pairs"}

    item_count_match = 0
    item_set_jaccards: list[float] = []
    for k in common:
        a_items = a_idx[k].get("items", [])
        b_items = b_idx[k].get("items", [])
        if len(a_items) == len(b_items):
            item_count_match += 1
        # Set of (item_type, counterparty_name) tuples
        a_set = {(it.get("item_type"), it.get("counterparty_name")) for it in a_items}
        b_set = {(it.get("item_type"), it.get("counterparty_name")) for it in b_items}
        item_set_jaccards.append(jaccard_similarity(a_set, b_set))

    return {
        "task": "register_of_interests_extraction",
        "rater_a": a_label,
        "rater_b": b_label,
        "common_section_n": len(common),
        "item_count_exact_match_rate": round(item_count_match / len(common), 4),
        "mean_item_set_jaccard": round(
            sum(item_set_jaccards) / len(item_set_jaccards), 4
        ),
        "median_item_set_jaccard": round(
            sorted(item_set_jaccards)[len(item_set_jaccards) // 2], 4
        ),
    }


def irr_entity_industry_classification(
    a_records: list[dict[str, Any]],
    b_records: list[dict[str, Any]],
    a_label: str,
    b_label: str,
) -> dict[str, Any]:
    """IRR for Stage 1 entity classification. Per-entity sector +
    entity_type + confidence."""
    a_idx = {r["entity_id"]: r for r in a_records if "public_sector" in r}
    b_idx = {r["entity_id"]: r for r in b_records if "public_sector" in r}
    common_ids = sorted(set(a_idx.keys()) & set(b_idx.keys()))
    if not common_ids:
        return {"error": "No overlapping entity_id between the two raters"}

    a = [a_idx[i] for i in common_ids]
    b = [b_idx[i] for i in common_ids]

    sector_a = [r["public_sector"] for r in a]
    sector_b = [r["public_sector"] for r in b]
    et_a = [r["new_entity_type"] for r in a]
    et_b = [r["new_entity_type"] for r in b]
    conf_a = [r["confidence"] for r in a]
    conf_b = [r["confidence"] for r in b]

    sector_kappa = cohens_kappa_nominal(sector_a, sector_b)
    et_kappa = cohens_kappa_nominal(et_a, et_b)
    conf_kappa = cohens_kappa_nominal(conf_a, conf_b)
    sector_per_class = per_class_kappa(sector_a, sector_b)

    return {
        "task": "entity_industry_classification",
        "rater_a": a_label,
        "rater_b": b_label,
        "common_n": len(common_ids),
        "public_sector": {
            **sector_kappa,
            "interpretation": kappa_interpretation(sector_kappa["kappa"]),
        },
        "entity_type": {
            **et_kappa,
            "interpretation": kappa_interpretation(et_kappa["kappa"]),
        },
        "confidence": {
            **conf_kappa,
            "interpretation": kappa_interpretation(conf_kappa["kappa"]),
        },
        "public_sector_per_class_kappa": sector_per_class,
    }


# -----------------------------------------------------------------
# CLI entry.
# -----------------------------------------------------------------


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _markdown_report(result: dict[str, Any]) -> str:
    """Render a JSON IRR result as a publication-quality Markdown
    report for the docs / GitHub mirror.
    """
    task = result.get("task", "?")
    a_label = result.get("rater_a", "?")
    b_label = result.get("rater_b", "?")
    n = (
        result.get("common_n")
        or result.get("common_section_n")
        or 0
    )
    lines = [
        f"# Inter-rater reliability — {task}",
        "",
        f"**Rater A:** {a_label}",
        f"**Rater B:** {b_label}",
        f"**Common-item N:** {n}",
        "",
        "## Methodology",
        "",
        "Sample is the FULL overlap set between Rater A and Rater B "
        "(every item where both raters returned a classification). "
        "No cherry-picking. Cohen's kappa is computed using the "
        "Landis-Koch (1977) interpretation thresholds:",
        "",
        "| κ | Interpretation |",
        "|---:|---|",
        "| ≥ 0.81 | almost perfect |",
        "| 0.61-0.80 | substantial |",
        "| 0.41-0.60 | moderate |",
        "| 0.21-0.40 | fair |",
        "| ≤ 0.20 | slight (or worse-than-chance) |",
        "",
        "For multi-label attributes (e.g. policy_topics), Jaccard "
        "similarity is reported per pair and averaged. Per-label "
        "Cohen's kappa, macro-F1, and micro-F1 are also reported.",
        "",
    ]
    if "sector" in result:
        s = result["sector"]
        lines += [
            "## Sector agreement",
            "",
            f"* Observed agreement: **{s['observed_agreement']}**",
            f"* Expected agreement (chance): {s['expected_agreement']}",
            f"* **Cohen's κ: {s['kappa']}** ({s['interpretation']})",
            "",
        ]
    if "public_sector" in result:
        s = result["public_sector"]
        lines += [
            "## Public-sector agreement",
            "",
            f"* Observed agreement: **{s['observed_agreement']}**",
            f"* Expected agreement (chance): {s['expected_agreement']}",
            f"* **Cohen's κ: {s['kappa']}** ({s['interpretation']})",
            "",
        ]
    if "procurement_class" in result:
        s = result["procurement_class"]
        lines += [
            "## Procurement-class agreement",
            "",
            f"* Observed agreement: **{s['observed_agreement']}**",
            f"* Expected agreement (chance): {s['expected_agreement']}",
            f"* **Cohen's κ: {s['kappa']}** ({s['interpretation']})",
            "",
        ]
    if "confidence" in result:
        s = result["confidence"]
        lines += [
            "## Confidence-label agreement",
            "",
            f"* Observed agreement: **{s['observed_agreement']}**",
            f"* Expected agreement (chance): {s['expected_agreement']}",
            f"* **Cohen's κ: {s['kappa']}** ({s['interpretation']})",
            "",
        ]
    if "policy_topics" in result and isinstance(result["policy_topics"], dict):
        pt = result["policy_topics"]
        lines += [
            "## Policy-topics agreement (multi-label)",
            "",
            f"* Mean Jaccard similarity: **{pt['mean_jaccard']}**",
            f"* Median Jaccard similarity: {pt['median_jaccard']}",
            f"* Macro-averaged per-label Cohen's κ: {pt['macro_kappa']}",
            f"* Macro-F1: {pt['macro_f1']}",
            f"* Micro-F1: {pt['micro_f1']}",
            "",
        ]
    if "item_count_exact_match_rate" in result:
        lines += [
            "## Item-count + item-set agreement (per section)",
            "",
            f"* Item-count exact match rate: **{result['item_count_exact_match_rate']}**",
            f"* Mean per-section item-set Jaccard (item_type × counterparty_name): **{result['mean_item_set_jaccard']}**",
            f"* Median per-section item-set Jaccard: {result['median_item_set_jaccard']}",
            "",
        ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compute inter-rater reliability (Cohen's kappa, Jaccard, "
            "multi-label F1) between two LLM raters on a shared item set."
        )
    )
    parser.add_argument(
        "--task", required=True,
        choices=[
            "austender_contract_topic_tag",
            "register_of_interests_extraction",
            "entity_industry_classification",
        ],
    )
    parser.add_argument("--rater-a-jsonl", required=True)
    parser.add_argument("--rater-a-label", required=True)
    parser.add_argument("--rater-b-jsonl", required=True)
    parser.add_argument("--rater-b-label", required=True)
    parser.add_argument(
        "--output-dir", default=None,
        help=(
            "Where to write the JSON + Markdown report. Default: "
            "data/audit/llm_inter_rater_reliability/<task>/"
        ),
    )
    args = parser.parse_args(argv)

    a_records = _read_jsonl(Path(args.rater_a_jsonl).resolve())
    b_records = _read_jsonl(Path(args.rater_b_jsonl).resolve())

    if args.task == "austender_contract_topic_tag":
        result = irr_austender_contract_topic_tag(
            a_records, b_records,
            args.rater_a_label, args.rater_b_label,
        )
    elif args.task == "register_of_interests_extraction":
        result = irr_register_of_interests(
            a_records, b_records,
            args.rater_a_label, args.rater_b_label,
        )
    else:
        result = irr_entity_industry_classification(
            a_records, b_records,
            args.rater_a_label, args.rater_b_label,
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else PROJECT_ROOT / "data" / "audit" / "llm_inter_rater_reliability" / args.task
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{timestamp}.json"
    md_path = output_dir / f"{timestamp}.md"

    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(_markdown_report(result), encoding="utf-8")

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print()
    print(_markdown_report(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
