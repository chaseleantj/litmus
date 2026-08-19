"""Can we score PARTS of a text (sentences / windows) and still match
whole-text detection quality at the document level?

Motivation: production scores one embedding per text projected onto the
human-AI axis (LOO AUC 0.820 at text-embedding-3-small @1536). A granular
method that scores individual sentences would let the UI show WHICH parts
of a text read AI vs human — but it is only useful if aggregating its
sentence scores back to a document score performs about as well.

Approaches evaluated (all at the document level, same leave-one-pair-out
protocol and metrics as embedding_dims.py, so numbers are directly
comparable to the 0.820 whole-text baseline):

1. sent-proj: split into sentences, embed each, project each sentence onto
   the human-AI direction learned (per fold, from training pairs only) from
   WHOLE-TEXT embeddings exactly like production. Aggregate to a doc score
   by mean / length-weighted mean / trimmed mean / median / top-3 extreme.
2. sent-centroid: same per-sentence projection, but the axis is learned in
   sentence space: human-sentence centroid minus AI-sentence centroid over
   the training pairs' sentences.
3. bertscore: BERTScore-style soft alignment. Each held-out sentence gets
   affinity = max cosine sim to the pool of training HUMAN sentences minus
   max cosine sim to the pool of training AI sentences (plus a
   softmax-weighted variant). Doc score = mean over sentences.
4. knn: each held-out sentence scored by its k=5 nearest training sentences
   (cosine), labels +1 human / -1 AI, similarity-weighted. Doc = mean.
5. window-proj: overlapping 3-sentence windows instead of single sentences
   (sentences may be too short for stable embeddings), projected onto the
   whole-text direction as in (1). Doc = mean over windows.

Leakage control: every fold rebuilds the direction / reference pools from
the 9 training pairs only; the held-out pair's text and sentences never
enter them.

Also prints a qualitative per-sentence heatmap (sentence text + score) for
a few held-out texts using the leakage-safe fold, to sanity-check that the
granular scores look meaningful.

Usage: python backend/experiments/granular_detection.py
Needs OPENROUTER_API_KEY (env var or repo .env). Embeddings cached in
embedding_cache.json (keyed by text hash), so reruns make no API calls.
Results saved to granular_detection_results.json.
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

RESULTS_PATH = EXPERIMENTS_DIR / "granular_detection_results.json"
DIM = 1536  # matches the production model's native size and the baseline run
MODEL = scoring.MODEL
KNN_K = 5
SOFTMAX_TEMP = 0.05
WINDOW = 3
# ---------------------------------------------------------------- text units

def split_sentences(text: str) -> list[str]:
    """The app's splitting rule (app.scoring.sentence_spans), so these numbers
    describe the units the product actually scores. Fragments shorter than
    scoring.MIN_SENT_CHARS join their neighbour: tiny fragments embed
    unstably."""
    return [text[a:b] for a, b in scoring.sentence_spans(text)]


def windows_of(sents: list[str], size: int = WINDOW) -> list[str]:
    if len(sents) <= size:
        return [" ".join(sents)]
    return [" ".join(sents[i:i + size]) for i in range(len(sents) - size + 1)]


# ---------------------------------------------------------------- aggregators

def agg_mean(scores, sents):
    return sum(scores) / len(scores)


def agg_len_weighted(scores, sents):
    w = [len(s) for s in sents]
    return sum(sc * wi for sc, wi in zip(scores, w)) / sum(w)


def agg_trimmed(scores, sents):
    """Mean with the single min and max dropped (when n >= 5)."""
    if len(scores) < 5:
        return agg_mean(scores, sents)
    s = sorted(scores)[1:-1]
    return sum(s) / len(s)


def agg_median(scores, sents):
    s = sorted(scores)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def agg_top3_extreme(scores, sents):
    """Mean of the 3 sentences with the largest |score| (most confident)."""
    top = sorted(scores, key=abs, reverse=True)[:3]
    return sum(top) / len(top)


AGGREGATORS = {
    "mean": agg_mean,
    "len-weighted": agg_len_weighted,
    "trimmed": agg_trimmed,
    "median": agg_median,
    "top3-extreme": agg_top3_extreme,
}


# --------------------------------------------------------- sentence scorers
# Each scorer: (unit_sent_vecs, refs) -> list of per-sentence scores.
# refs is a per-fold dict built from training pairs only.

def centroid_axis(h_vecs, a_vecs):
    dims = len(h_vecs[0])
    h_c = [sum(v[d] for v in h_vecs) / len(h_vecs) for d in range(dims)]
    a_c = [sum(v[d] for v in a_vecs) / len(a_vecs) for d in range(dims)]
    direction = [h - a for h, a in zip(h_c, a_c)]
    length = math.hypot(*direction)
    unit = [x / length for x in direction]
    mid = [(h + a) / 2 for h, a in zip(h_c, a_c)]
    return unit, scoring.dot(mid, unit)


def score_projection(vecs, unit, bias):
    return [scoring.dot(v, unit) - bias for v in vecs]


def score_bertscore(vecs, h_pool, a_pool, mode: str):
    out = []
    for v in vecs:
        h_sims = [scoring.dot(v, r) for r in h_pool]
        a_sims = [scoring.dot(v, r) for r in a_pool]
        if mode == "max":
            out.append(max(h_sims) - max(a_sims))
        else:  # softmax-weighted average similarity
            def soft(sims):
                ws = [math.exp(s / SOFTMAX_TEMP) for s in sims]
                z = sum(ws)
                return sum(w * s for w, s in zip(ws, sims)) / z
            out.append(soft(h_sims) - soft(a_sims))
    return out


def score_knn(vecs, h_pool, a_pool, k: int = KNN_K):
    labeled = [(r, 1.0) for r in h_pool] + [(r, -1.0) for r in a_pool]
    out = []
    for v in vecs:
        sims = sorted(
            ((scoring.dot(v, r), lab) for r, lab in labeled), reverse=True
        )[:k]
        out.append(sum(s * lab for s, lab in sims) / sum(s for s, _ in sims))
    return out


# ------------------------------------------------------------------ pipeline

def main() -> None:
    pairs = [
        (row["ai"], row["human"])
        for row in json.loads((REPO_ROOT / "examples.json").read_text())
    ]
    n = len(pairs)
    print(f"Dataset: {n} AI/human pairs from examples.json; model {MODEL} @{DIM}")
    print("Protocol: leave-one-pair-out at the DOCUMENT level; per-fold "
          "directions/pools from training pairs only\n")

    api_key = scoring.load_api_key()
    cache = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}

    def embed(texts: list[str]) -> list[list[float]]:
        return embed_at_dim(texts, DIM, api_key, cache, model=MODEL)

    # Precompute all embeddings (cache-first): whole texts, sentences, windows.
    doc_texts = [t for ai, h in pairs for t in (ai, h)]
    ai_docs = embed(doc_texts)[0::2]
    h_docs = embed(doc_texts)[1::2]
    ai_sents = [split_sentences(ai) for ai, _ in pairs]
    h_sents = [split_sentences(h) for _, h in pairs]
    all_sents = [s for group in ai_sents + h_sents for s in group]
    embed(all_sents)  # warm cache in one batch
    ai_svecs = [embed(g) for g in ai_sents]
    h_svecs = [embed(g) for g in h_sents]
    ai_wins = [windows_of(g) for g in ai_sents]
    h_wins = [windows_of(g) for g in h_sents]
    embed([w for group in ai_wins + h_wins for w in group])
    ai_wvecs = [embed(g) for g in ai_wins]
    h_wvecs = [embed(g) for g in h_wins]

    # Per-fold sentence scores for every method, so aggregators can share them.
    # method -> fold i -> (ai_scores_per_unit, human_scores_per_unit)
    methods = ["sent-proj", "sent-centroid", "bertscore-max",
               "bertscore-soft", "knn", "window-proj"]
    unit_scores = {m: [] for m in methods}
    for i in range(n):
        tr = [j for j in range(n) if j != i]
        unit_doc, bias_doc = learn_direction_from_vectors(
            [h_docs[j] for j in tr], [ai_docs[j] for j in tr]
        )
        h_pool = [v for j in tr for v in h_svecs[j]]
        a_pool = [v for j in tr for v in ai_svecs[j]]
        unit_cen, bias_cen = centroid_axis(h_pool, a_pool)

        for m in methods:
            def score(vecs):
                if m == "sent-proj":
                    return score_projection(vecs, unit_doc, bias_doc)
                if m == "sent-centroid":
                    return score_projection(vecs, unit_cen, bias_cen)
                if m == "bertscore-max":
                    return score_bertscore(vecs, h_pool, a_pool, "max")
                if m == "bertscore-soft":
                    return score_bertscore(vecs, h_pool, a_pool, "soft")
                if m == "knn":
                    return score_knn(vecs, h_pool, a_pool)
                return score_projection(vecs, unit_doc, bias_doc)  # window-proj
            if m == "window-proj":
                unit_scores[m].append((score(ai_wvecs[i]), score(h_wvecs[i])))
            else:
                unit_scores[m].append((score(ai_svecs[i]), score(h_svecs[i])))

    # Whole-text baseline row, recomputed here for the same table.
    h_doc_scores, ai_doc_scores, wins = [], [], 0
    for i in range(n):
        tr = [j for j in range(n) if j != i]
        u, b = learn_direction_from_vectors(
            [h_docs[j] for j in tr], [ai_docs[j] for j in tr]
        )
        hs = scoring.dot(h_docs[i], u) - b
        as_ = scoring.dot(ai_docs[i], u) - b
        h_doc_scores.append(hs)
        ai_doc_scores.append(as_)
        wins += hs > as_
    rows = [{
        "approach": "whole-text (baseline)", "aggregation": "-",
        "auc": roc_auc(h_doc_scores, ai_doc_scores),
        "d_prime": d_prime(h_doc_scores, ai_doc_scores),
        "paired_accuracy": wins / n,
    }]

    # Aggregate each method's per-unit scores to document scores.
    for m in methods:
        aggs = AGGREGATORS if m != "window-proj" else {
            "mean": agg_mean, "len-weighted": agg_len_weighted}
        for agg_name, agg in aggs.items():
            h_scores, a_scores, wins = [], [], 0
            for i in range(n):
                a_units, h_units = unit_scores[m][i]
                a_texts = ai_wins[i] if m == "window-proj" else ai_sents[i]
                h_texts = h_wins[i] if m == "window-proj" else h_sents[i]
                hs = agg(h_units, h_texts)
                as_ = agg(a_units, a_texts)
                h_scores.append(hs)
                a_scores.append(as_)
                wins += hs > as_
            rows.append({
                "approach": m, "aggregation": agg_name,
                "auc": roc_auc(h_scores, a_scores),
                "d_prime": d_prime(h_scores, a_scores),
                "paired_accuracy": wins / n,
            })

    header = (f"{'approach':<22} {'aggregation':<13} {'LOO AUC':>8} "
              f"{'d-prime':>8} {'paired acc':>10}")
    print(header)
    print("-" * len(header))
    for r in rows:
        print(f"{r['approach']:<22} {r['aggregation']:<13} {r['auc']:>8.3f} "
              f"{r['d_prime']:>8.2f} {r['paired_accuracy']:>10.0%}")

    # ------------------------------------------------ qualitative heatmaps
    # Show per-sentence scores for a few held-out texts (fold = their own
    # pair held out, so the display is leakage-safe). Positive = more human.
    show = [(7, "ai"), (7, "human"), (5, "ai")]
    samples = []
    for method in ("sent-proj", "bertscore-soft"):
        print(f"\nPer-sentence scores ({method}, held-out fold; + human / - AI)")
        for i, side in show:
            a_units, h_units = unit_scores[method][i]
            units = a_units if side == "ai" else h_units
            sents = ai_sents[i] if side == "ai" else h_sents[i]
            print(f"\n--- pair {i}, {side.upper()} text ---")
            for s, sc in zip(sents, units):
                snippet = s if len(s) <= 90 else s[:87] + "..."
                print(f"  {sc:+.4f}  {snippet}")
            samples.append({
                "method": method, "pair": i, "side": side,
                "sentences": [{"text": s, "score": sc}
                              for s, sc in zip(sents, units)],
            })

    RESULTS_PATH.write_text(json.dumps({
        "model": MODEL, "dim": DIM, "n_pairs": n,
        "protocol": "leave-one-pair-out (document level)",
        "results": rows, "heatmap_samples": samples,
    }, indent=2))
    print(f"\nSaved to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
