"""Was top-3-extreme a real winner or an artifact of trying only 5 aggregations?

Sweeps a much larger family of sentence-score -> document-score aggregations
for the two granular methods that matched the whole-text baseline in
granular_detection.py (bertscore-soft and sent-proj), under the identical
leave-one-pair-out protocol:

  - top-k extreme: mean of the k sentences with the largest |score|, for
    k = 1, 2, 3, 4, 5, 7, 10 (capped at the sentence count) and k = all
    (plain mean), plus fractional top-25% / top-50% (ceil, min 1).
  - weighted means over ALL sentences: |score|-weighted (magnitude),
    softmax(|score|/T) for T in {0.02, 0.05, 0.1}, and linearly decaying
    weights on the extremeness rank (most extreme sentence gets weight n,
    least extreme weight 1).
  - references: trimmed mean and median from the original table.

Stability reporting (differences are tiny at n=10 pairs, i.e. 100 human-vs-AI
comparisons, so 1 flipped comparison = 0.01 AUC):
  - the full AUC-vs-k curve per method (smooth plateau = robust; an isolated
    spike at one k = we overfit the choice);
  - for the top aggregations, the number of individual (human, AI) comparison
    outcomes that differ between each pair of aggregations.

Runs entirely from embedding_cache.json — zero API calls (a dummy key is
passed; the cache covers every text). Results saved to
aggregation_sweep_results.json.

Usage: python backend/experiments/aggregation_sweep.py
"""

from __future__ import annotations

import json
import math

from embedding_dims import (
    CACHE_PATH,
    EXPERIMENTS_DIR,
    REPO_ROOT,
    d_prime,
    embed_at_dim,
    learn_direction_from_vectors,
    roc_auc,
    scoring,
)
from granular_detection import (
    DIM,
    MODEL,
    score_bertscore,
    score_projection,
    split_sentences,
)

RESULTS_PATH = EXPERIMENTS_DIR / "aggregation_sweep_results.json"
TOP_KS = [1, 2, 3, 4, 5, 7, 10]
SOFTMAX_TEMPS = [0.02, 0.05, 0.1]


# ---------------------------------------------------------------- aggregators

def by_extremeness(scores: list[float]) -> list[float]:
    return sorted(scores, key=abs, reverse=True)


def make_topk(k: int):
    def agg(scores: list[float]) -> float:
        top = by_extremeness(scores)[: min(k, len(scores))]
        return sum(top) / len(top)
    return agg


def make_topfrac(frac: float):
    def agg(scores: list[float]) -> float:
        k = max(1, math.ceil(frac * len(scores)))
        top = by_extremeness(scores)[:k]
        return sum(top) / len(top)
    return agg


def agg_magnitude_weighted(scores: list[float]) -> float:
    w = [abs(s) for s in scores]
    z = sum(w)
    if z == 0:
        return sum(scores) / len(scores)
    return sum(s * wi for s, wi in zip(scores, w)) / z


def make_softmax_weighted(temp: float):
    def agg(scores: list[float]) -> float:
        m = max(abs(s) for s in scores)
        w = [math.exp((abs(s) - m) / temp) for s in scores]
        z = sum(w)
        return sum(s * wi for s, wi in zip(scores, w)) / z
    return agg


def agg_rank_linear(scores: list[float]) -> float:
    """Linearly decaying weights on the extremeness ranking: most extreme
    sentence gets weight n, least extreme gets 1."""
    ranked = by_extremeness(scores)
    n = len(ranked)
    w = list(range(n, 0, -1))
    return sum(s * wi for s, wi in zip(ranked, w)) / sum(w)


def agg_mean(scores: list[float]) -> float:
    return sum(scores) / len(scores)


def agg_trimmed(scores: list[float]) -> float:
    if len(scores) < 5:
        return agg_mean(scores)
    s = sorted(scores)[1:-1]
    return sum(s) / len(s)


def agg_median(scores: list[float]) -> float:
    s = sorted(scores)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


AGGREGATORS: dict[str, callable] = {
    **{f"top-{k}": make_topk(k) for k in TOP_KS},
    "mean (k=all)": agg_mean,
    "top-25%": make_topfrac(0.25),
    "top-50%": make_topfrac(0.50),
    "|s|-weighted": agg_magnitude_weighted,
    **{f"softmax T={t}": make_softmax_weighted(t) for t in SOFTMAX_TEMPS},
    "rank-linear": agg_rank_linear,
    "trimmed": agg_trimmed,
    "median": agg_median,
}


# ------------------------------------------------------------------ pipeline

def main() -> None:
    pairs = [
        (row["ai"], row["human"])
        for row in json.loads((REPO_ROOT / "examples.json").read_text())
    ]
    n = len(pairs)
    cache = json.loads(CACHE_PATH.read_text())

    def embed(texts: list[str]) -> list[list[float]]:
        # Dummy key: every text is already in the cache, so no API call is
        # made. A cache miss would fail loudly (401) rather than silently.
        return embed_at_dim(texts, DIM, "dummy-key-cache-only", cache, model=MODEL)

    ai_docs = embed([ai for ai, _ in pairs])
    h_docs = embed([h for _, h in pairs])
    ai_sents = [split_sentences(ai) for ai, _ in pairs]
    h_sents = [split_sentences(h) for _, h in pairs]
    ai_svecs = [embed(g) for g in ai_sents]
    h_svecs = [embed(g) for g in h_sents]

    # Per-fold per-sentence scores, identical to granular_detection.py.
    methods = ["bertscore-soft", "sent-proj"]
    unit_scores: dict[str, list[tuple[list[float], list[float]]]] = {
        m: [] for m in methods
    }
    for i in range(n):
        tr = [j for j in range(n) if j != i]
        unit_doc, bias_doc = learn_direction_from_vectors(
            [h_docs[j] for j in tr], [ai_docs[j] for j in tr]
        )
        h_pool = [v for j in tr for v in h_svecs[j]]
        a_pool = [v for j in tr for v in ai_svecs[j]]
        unit_scores["bertscore-soft"].append((
            score_bertscore(ai_svecs[i], h_pool, a_pool, "soft"),
            score_bertscore(h_svecs[i], h_pool, a_pool, "soft"),
        ))
        unit_scores["sent-proj"].append((
            score_projection(ai_svecs[i], unit_doc, bias_doc),
            score_projection(h_svecs[i], unit_doc, bias_doc),
        ))

    sent_counts = sorted(len(g) for g in ai_sents + h_sents)
    print(f"Dataset: {n} pairs; sentence counts per text: {sent_counts}")
    print("Protocol: leave-one-pair-out (document level), from cache only\n")

    # Evaluate every (method, aggregation).
    results = []
    doc_scores: dict[tuple[str, str], tuple[list[float], list[float]]] = {}
    for m in methods:
        for name, agg in AGGREGATORS.items():
            h_sc, a_sc, wins = [], [], 0
            for i in range(n):
                a_units, h_units = unit_scores[m][i]
                hs, as_ = agg(h_units), agg(a_units)
                h_sc.append(hs)
                a_sc.append(as_)
                wins += hs > as_
            doc_scores[(m, name)] = (h_sc, a_sc)
            results.append({
                "method": m, "aggregation": name,
                "auc": roc_auc(h_sc, a_sc),
                "d_prime": d_prime(h_sc, a_sc),
                "paired_accuracy": wins / n,
            })

    for m in methods:
        header = (f"{m:<16} {'aggregation':<14} {'LOO AUC':>8} "
                  f"{'d-prime':>8} {'paired acc':>10}")
        print(header)
        print("-" * len(header))
        for r in results:
            if r["method"] == m:
                print(f"{'':<16} {r['aggregation']:<14} {r['auc']:>8.3f} "
                      f"{r['d_prime']:>8.2f} {r['paired_accuracy']:>10.0%}")
        print()

    # ------------------------------------------------------- stability views
    print("AUC vs k (top-k extreme; k=all is the plain mean)")
    ks = [str(k) for k in TOP_KS] + ["all"]
    print(f"{'k':>14}  " + "  ".join(f"{k:>5}" for k in ks))
    for m in methods:
        aucs = [next(r["auc"] for r in results
                     if r["method"] == m and r["aggregation"] == label)
                for label in [f"top-{k}" for k in TOP_KS] + ["mean (k=all)"]]
        print(f"{m:>14}  " + "  ".join(f"{a:>5.2f}" for a in aucs))

    # Comparison-outcome deltas between top aggregations: how many of the
    # n*n (human, AI) orderings differ. 1 flip = 0.01 AUC at n=10.
    def outcomes(key):
        h_sc, a_sc = doc_scores[key]
        return [h > a for h in h_sc for a in a_sc]

    print("\nPairwise flipped (human, AI) comparisons out of "
          f"{n * n} (per method, top aggregations by AUC):")
    flip_tables = {}
    for m in methods:
        top = sorted((r for r in results if r["method"] == m),
                     key=lambda r: -r["auc"])[:5]
        names = [r["aggregation"] for r in top]
        print(f"\n{m}: " + ", ".join(
            f"{r['aggregation']} ({r['auc']:.2f})" for r in top))
        table = {}
        for x in range(len(names)):
            for y in range(x + 1, len(names)):
                ox, oy = outcomes((m, names[x])), outcomes((m, names[y]))
                flips = sum(a != b for a, b in zip(ox, oy))
                table[f"{names[x]} vs {names[y]}"] = flips
                print(f"  {names[x]:<14} vs {names[y]:<14}: {flips} flips")
        flip_tables[m] = table

    RESULTS_PATH.write_text(json.dumps({
        "model": MODEL, "dim": DIM, "n_pairs": n,
        "protocol": "leave-one-pair-out (document level)",
        "sentence_counts": sent_counts,
        "results": results,
        "flipped_comparisons": flip_tables,
    }, indent=2))
    print(f"\nSaved to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
