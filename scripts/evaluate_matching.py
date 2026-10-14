#!/usr/bin/env python3
"""Measure top-k retrieval on LostLink's labelled synthetic benchmark."""
from __future__ import annotations
import argparse
import json
import os
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests" / "data" / "matching_benchmark.json"


def load_cases():
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    cases = payload["cases"]
    if len(cases) != 15:
        raise ValueError(f"Expected 15 labelled cases, got {len(cases)}")
    for case in cases:
        candidate_ids = {item["id"] for item in case["candidates"]}
        if not set(case["relevant_ids"]).issubset(candidate_ids):
            raise ValueError(f"Invalid positive label in {case['case_id']}")
    return cases, payload["description"]


def evaluate(engine, cases):
    hits = {1: 0, 3: 0}
    reciprocal_ranks = []
    engine_counts = Counter()
    pair_count = 0
    for case in cases:
        ranked = engine.rank(case["lost"], case["candidates"], limit=len(case["candidates"]))
        pair_count += len(case["candidates"])
        for item in ranked:
            engine_counts[item.get("engine", "unknown")] += 1
        relevant = set(case["relevant_ids"])
        ranks = [i for i, item in enumerate(ranked, 1) if item["report"]["id"] in relevant]
        rank = min(ranks) if ranks else None
        if rank == 1:
            hits[1] += 1
        if rank is not None and rank <= 3:
            hits[3] += 1
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)
    total = len(cases)
    return {
        "queries": total,
        "candidate_pairs_scored": pair_count,
        "top1_hits": hits[1],
        "top1_hit_rate_percent": round(100 * hits[1] / total, 1),
        "top3_hits": hits[3],
        "top3_hit_rate_percent": round(100 * hits[3] / total, 1),
        "mean_reciprocal_rank": round(sum(reciprocal_ranks) / total, 4),
        "engine_counts": dict(engine_counts),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-semantic-model", action="store_true")
    args = parser.parse_args()
    cases, description = load_cases()
    os.environ["USE_CLIP_MODEL"] = "false"
    os.environ["USE_SEMANTIC_MODEL"] = "false"
    from app.matching import MatchingEngine

    baseline = MatchingEngine()
    baseline.semantic_enabled = False
    baseline.clip_enabled = False
    baseline_result = evaluate(baseline, cases)

    semantic = MatchingEngine()
    semantic.semantic_enabled = True
    semantic.clip_enabled = False
    semantic_result = evaluate(semantic, cases)
    model_loaded = semantic._text_model is not None

    output = {
        "benchmark_description": description,
        "data_status": "synthetic labelled development data; not campus ground truth",
        "requested_setting": "USE_SEMANTIC_MODEL=true",
        "semantic_model": os.getenv("SEMANTIC_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
        "baseline": baseline_result,
        "semantic": {
            "available": model_loaded,
            **(semantic_result if model_loaded else {
                "top3_hit_rate_percent": None,
                "note": "Model did not load; semantic top-3 is not reported."
            }),
        },
    }
    print(json.dumps(output, indent=2))
    if args.require_semantic_model and not model_loaded:
        raise SystemExit("Sentence Transformers did not load; refusing to claim a semantic score.")


if __name__ == "__main__":
    main()
