"""Offline retrieval strategy comparison using the current fresh-holdout report."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "docs" / "project" / "v3.2-fresh-paraphrase-diagnostic.json"
REPORT = ROOT / ".tmp" / "nvidia_embedding_fresh_holdout_eval.json"
OUT = ROOT / ".tmp" / "nvidia_embedding_strategy_eval.json"


def metrics(cases, rankings):
    result = {}
    for k in (1, 3, 5, 10):
        result[f"recall_at_{k}"] = round(
            sum(c["expected_uri"] in rankings[c["id"]][:k] for c in cases) / len(cases), 4
        )
    reciprocal_ranks = []
    for case in cases:
        ranked = rankings[case["id"]]
        reciprocal_ranks.append(
            1 / (ranked.index(case["expected_uri"]) + 1)
            if case["expected_uri"] in ranked else 0
        )
    result["mrr"] = round(sum(reciprocal_ranks) / len(cases), 4)
    return result


def main():
    cases = json.loads(BENCHMARK.read_text(encoding="utf-8"))["cases"]
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    fts = {x["id"]: x["top10"] for x in report["fts5"]["cases"]}
    vector = {x["id"]: x["top10"] for x in report["vector"]["cases"]}
    methods = {"fts5": fts, "vector": vector}

    for n in (3, 5, 7):
        ranked = {}
        for case in cases:
            ordered = list(vector[case["id"]][:n])
            ordered.extend(uri for uri in fts[case["id"]] if uri not in ordered)
            ranked[case["id"]] = ordered[:10]
        methods[f"vector_first_{n}_fts_fill"] = ranked

    rrf = {}
    for case in cases:
        scores = {}
        for source in (fts, vector):
            for rank, uri in enumerate(source[case["id"]], 1):
                scores[uri] = scores.get(uri, 0) + 1 / (60 + rank)
        rrf[case["id"]] = [uri for uri, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:10]]
    methods["rrf_k60"] = rrf

    output = {
        "benchmark": "v3.2-fresh-paraphrase-diagnostic.json",
        "note": "Only the fresh holdout is included; the current full-corpus report does not persist FTS candidate lists.",
        "methods": {name: metrics(cases, ranks) for name, ranks in methods.items()},
    }
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, result in output["methods"].items():
        print(name, json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
