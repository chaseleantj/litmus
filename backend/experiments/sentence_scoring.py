"""Does scoring every sentence and aggregating beat scoring the whole text?

Production embeds a text once and projects that single vector onto the
human-AI axis (scoring.project_score). This experiment replaces that with:
split the text into sentences, embed each sentence, project each one, then
collapse the per-sentence scores into one document score with an explicit
aggregation rule (mean, length-weighted, position-weighted, median, trimmed,
top-k extreme, softmax, ...).

Two ways of getting the axis are tried, because the axis and the units it
scores need not live in the same space:
  - doc-axis: the axis is learned exactly as production learns it, from
    WHOLE-TEXT embeddings of the training pairs. Only the thing being
    projected changes.
  - sent-axis: the axis is the human-sentence centroid minus the
    AI-sentence centroid over the training pairs' sentences, midpoint
    centered. Matches units to axis.

Dataset: the live library in backend/data/app.db (falls back to
examples.json). Protocol: leave-one-pair-out — each pair is held out in
turn, the axis (and, for sent-axis, the sentence pools) is rebuilt from the
remaining pairs only, and both held-out texts are scored. Nothing from the
held-out pair enters the fit.

Metrics, all on the pooled held-out scores:
  - LOO ROC-AUC: P(a random human text outscores a random AI text). The
    headline separation number; rank-based, so immune to the score-scale
    differences between aggregations. 95% CI by bootstrap over pairs
    (pairs resampled with replacement, both texts moving together, on the
    stored held-out scores — the folds are not refit, so the interval
    reflects sampling of pairs, not of the fitting procedure).
  - d': standardized mean gap, as an effect size.
  - paired accuracy: fraction of pairs whose human version outscores its
    own AI version. This is what the product actually shows a user.
  - vs baseline: how many of the n*n human-vs-AI comparisons flip relative
    to whole-text, split into gains and losses, with an exact two-sided
    sign test on the discordant comparisons. At this n most AUC gaps are
    worth less than a couple of flipped comparisons, and the test says so.

Usage: python backend/experiments/sentence_scoring.py
Needs OPENROUTER_API_KEY (env var or repo .env). Embeddings are cached in
embedding_cache.json, so reruns make no API calls. Results are printed and
saved to sentence_scoring_results.json.
"""

from __future__ import annotations

import json
import math
import random
import sqlite3

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
from granular_detection import DIM, MODEL, split_sentences

RESULTS_PATH = EXPERIMENTS_DIR / "sentence_scoring_results.json"
DB_PATH = REPO_ROOT / "backend" / "data" / "app.db"
BOOTSTRAP_ROUNDS = 10000
BOOTSTRAP_SEED = 12345


# ------------------------------------------------------------------- dataset

def load_pairs() -> tuple[list[tuple[str, str]], str]:
    """(ai, human) pairs from the live library, or examples.json if there is
    no database (a fresh checkout, or CI)."""
    # data/ is gitignored, so a worktree has no database of its own; fall back
    # to the main checkout's, which is the library the app actually serves.
    for path in (DB_PATH, REPO_ROOT.parent / "main" / "backend" / "data" / "app.db"):
        if path.exists():
            con = sqlite3.connect(path)
            rows = con.execute(
                "SELECT ai, human FROM examples ORDER BY id"
            ).fetchall()
            con.close()
            if rows:
                return [(ai, human) for ai, human in rows], str(path)
    rows = json.loads((REPO_ROOT / "examples.json").read_text())
    return [(r["ai"], r["human"]) for r in rows], "examples.json"


# --------------------------------------------------------------- aggregators
# Each takes the per-sentence scores and the sentences they came from, and
# returns one document score.

def by_extremeness(scores: list[float]) -> list[float]:
    return sorted(scores, key=abs, reverse=True)


def agg_mean(scores, sents):
    return sum(scores) / len(scores)


def agg_len_weighted(scores, sents):
    w = [len(s) for s in sents]
    return sum(s * wi for s, wi in zip(scores, w)) / sum(w)


def agg_median(scores, sents):
    s = sorted(scores)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def agg_trimmed(scores, sents):
    """Mean with the single min and max dropped (needs n >= 5)."""
    if len(scores) < 5:
        return agg_mean(scores, sents)
    s = sorted(scores)[1:-1]
    return sum(s) / len(s)


def make_topk(k: int):
    def agg(scores, sents):
        top = by_extremeness(scores)[: min(k, len(scores))]
        return sum(top) / len(top)
    return agg


def make_topfrac(frac: float):
    def agg(scores, sents):
        k = max(1, math.ceil(frac * len(scores)))
        top = by_extremeness(scores)[:k]
        return sum(top) / len(top)
    return agg


def agg_magnitude_weighted(scores, sents):
    w = [abs(s) for s in scores]
    z = sum(w)
    if z == 0:
        return agg_mean(scores, sents)
    return sum(s * wi for s, wi in zip(scores, w)) / z


def make_softmax(temp: float):
    def agg(scores, sents):
        m = max(abs(s) for s in scores)
        w = [math.exp((abs(s) - m) / temp) for s in scores]
        z = sum(w)
        return sum(s * wi for s, wi in zip(scores, w)) / z
    return agg


def agg_rank_linear(scores, sents):
    """Linearly decaying weights on the extremeness ranking: the most extreme
    sentence gets weight n, the least extreme 1."""
    ranked = by_extremeness(scores)
    n = len(ranked)
    w = [n - i for i in range(n)]
    return sum(s * wi for s, wi in zip(ranked, w)) / sum(w)


def make_position_weighted(mode: str):
    """Position matters for voice: openings and closings are where a
    ghost-written text usually gives itself away. 'first' weights sentence i
    by n-i, 'last' by i+1."""
    def agg(scores, sents):
        n = len(scores)
        w = [n - i for i in range(n)] if mode == "first" else [i + 1 for i in range(n)]
        return sum(s * wi for s, wi in zip(scores, w)) / sum(w)
    return agg


def agg_min(scores, sents):
    """The most AI-sounding sentence decides — a text is only as human as its
    worst line."""
    return min(scores)


def agg_max(scores, sents):
    return max(scores)


AGGREGATORS = {
    "mean": agg_mean,
    "len-weighted": agg_len_weighted,
    "median": agg_median,
    "trimmed": agg_trimmed,
    "top-1 extreme": make_topk(1),
    "top-2 extreme": make_topk(2),
    "top-3 extreme": make_topk(3),
    "top-4 extreme": make_topk(4),
    "top-5 extreme": make_topk(5),
    "top-25% extreme": make_topfrac(0.25),
    "top-50% extreme": make_topfrac(0.50),
    "|s|-weighted": agg_magnitude_weighted,
    "softmax T=0.05": make_softmax(0.05),
    "softmax T=0.1": make_softmax(0.1),
    "rank-linear": agg_rank_linear,
    "position first": make_position_weighted("first"),
    "position last": make_position_weighted("last"),
    "min (worst line)": agg_min,
    "max (best line)": agg_max,
}


# ------------------------------------------------------------------ axis math

def centroid_axis(h_vecs, a_vecs):
    """Human centroid minus AI centroid, unit length, midpoint centered.
    Used for the sentence-space axis, where sentences are not paired."""
    dims = len(h_vecs[0])
    h_c = [sum(v[d] for v in h_vecs) / len(h_vecs) for d in range(dims)]
    a_c = [sum(v[d] for v in a_vecs) / len(a_vecs) for d in range(dims)]
    direction = [h - a for h, a in zip(h_c, a_c)]
    unit = [x / math.hypot(*direction) for x in direction]
    mid = [(h + a) / 2 for h, a in zip(h_c, a_c)]
    return unit, scoring.dot(mid, unit)


def project(vecs, unit, bias):
    return [scoring.dot(v, unit) - bias for v in vecs]


# -------------------------------------------------------------------- stats

def bootstrap_auc_ci(human: list[float], ai: list[float]) -> tuple[float, float]:
    """Percentile 95% CI for the AUC, resampling PAIRS with replacement so a
    pair's human and AI text always move together."""
    rng = random.Random(BOOTSTRAP_SEED)
    n = len(human)
    idx = range(n)
    aucs = []
    for _ in range(BOOTSTRAP_ROUNDS):
        pick = [rng.choice(idx) for _ in range(n)]
        aucs.append(roc_auc([human[i] for i in pick], [ai[i] for i in pick]))
    aucs.sort()
    lo = aucs[int(0.025 * BOOTSTRAP_ROUNDS)]
    hi = aucs[min(int(0.975 * BOOTSTRAP_ROUNDS), BOOTSTRAP_ROUNDS - 1)]
    return lo, hi


def comparison_outcomes(human: list[float], ai: list[float]) -> list[float]:
    """One entry per (human, AI) comparison: 1 correct, 0 wrong, 0.5 tie.
    The units AUC is an average of, so two methods can be compared
    comparison by comparison."""
    return [(h > a) + 0.5 * (h == a) for h in human for a in ai]


def sign_test_p(gains: int, losses: int) -> float:
    """Exact two-sided sign test on the discordant comparisons. Treats them as
    independent, which they are not (each text appears in n comparisons), so
    read it as a lower bound on the p-value — an optimistic screen. If it is
    not significant here, it is not significant."""
    n = gains + losses
    if n == 0:
        return 1.0
    k = min(gains, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * tail)


def summarize(
    name: str,
    human: list[float],
    ai: list[float],
    baseline: list[float] | None,
) -> dict:
    auc = roc_auc(human, ai)
    lo, hi = bootstrap_auc_ci(human, ai)
    out = {
        "method": name,
        "auc": auc,
        "auc_ci95": [lo, hi],
        "d_prime": d_prime(human, ai),
        "paired_accuracy": sum(h > a for h, a in zip(human, ai)) / len(human),
        "human_scores": human,
        "ai_scores": ai,
    }
    outcomes = comparison_outcomes(human, ai)
    out["outcomes"] = outcomes
    if baseline is not None:
        gains = sum(o > b for o, b in zip(outcomes, baseline))
        losses = sum(o < b for o, b in zip(outcomes, baseline))
        out.update(
            {
                "gains_vs_baseline": gains,
                "losses_vs_baseline": losses,
                "sign_test_p": sign_test_p(gains, losses),
            }
        )
    return out


# ------------------------------------------------------------------ pipeline

def main() -> None:
    pairs, source = load_pairs()
    n = len(pairs)
    sents = [(split_sentences(ai), split_sentences(h)) for ai, h in pairs]
    counts = [len(s) for pair in sents for s in pair]

    print(f"Dataset: {n} AI/human pairs ({2 * n} texts) from {source}")
    print(f"Model: {MODEL} @{DIM}")
    print(
        f"Sentences per text: min {min(counts)}, median "
        f"{sorted(counts)[len(counts) // 2]}, max {max(counts)}, "
        f"{sum(counts)} total"
    )
    print(
        "Protocol: leave-one-pair-out; axis (and sentence pools) rebuilt per "
        "fold from training pairs only\n"
    )

    api_key = scoring.load_api_key()
    cache = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}

    def embed(texts):
        return embed_at_dim(texts, DIM, api_key, cache, model=MODEL)

    # Whole-text vectors, and one vector per sentence of every text.
    docs = embed([t for ai, h in pairs for t in (ai, h)])
    ai_docs, h_docs = docs[0::2], docs[1::2]
    flat = [s for pair in sents for text_sents in pair for s in text_sents]
    flat_vecs = embed(flat)
    cursor = 0
    sent_vecs: list[tuple[list, list]] = []
    for ai_s, h_s in sents:
        a = flat_vecs[cursor:cursor + len(ai_s)]
        cursor += len(ai_s)
        h = flat_vecs[cursor:cursor + len(h_s)]
        cursor += len(h_s)
        sent_vecs.append((a, h))

    # Every method's held-out scores, filled fold by fold.
    keys = ["whole-text"] + [
        f"{axis}|{agg}" for axis in ("doc-axis", "sent-axis") for agg in AGGREGATORS
    ]
    scores = {k: {"human": [], "ai": []} for k in keys}

    for i in range(n):
        train = [j for j in range(n) if j != i]
        doc_unit, doc_bias = learn_direction_from_vectors(
            [h_docs[j] for j in train], [ai_docs[j] for j in train]
        )
        sent_unit, sent_bias = centroid_axis(
            [v for j in train for v in sent_vecs[j][1]],
            [v for j in train for v in sent_vecs[j][0]],
        )

        scores["whole-text"]["human"].append(
            scoring.dot(h_docs[i], doc_unit) - doc_bias
        )
        scores["whole-text"]["ai"].append(
            scoring.dot(ai_docs[i], doc_unit) - doc_bias
        )

        for axis, (unit, bias) in (
            ("doc-axis", (doc_unit, doc_bias)),
            ("sent-axis", (sent_unit, sent_bias)),
        ):
            per_sent = {
                "human": (project(sent_vecs[i][1], unit, bias), sents[i][1]),
                "ai": (project(sent_vecs[i][0], unit, bias), sents[i][0]),
            }
            for agg_name, agg in AGGREGATORS.items():
                for side, (ss, tt) in per_sent.items():
                    scores[f"{axis}|{agg_name}"][side].append(agg(ss, tt))

    baseline = comparison_outcomes(
        scores["whole-text"]["human"], scores["whole-text"]["ai"]
    )
    results = [
        summarize("whole-text (production)", *scores["whole-text"].values(), None)
    ] + [
        summarize(k, scores[k]["human"], scores[k]["ai"], baseline)
        for k in keys[1:]
    ]

    base = results[0]
    header = (
        f"{'method':<28}{'AUC':>7}{'95% CI':>16}{'d-prime':>9}"
        f"{'paired':>8}{'+/- vs base':>13}{'sign p':>8}"
    )
    print(header)
    print("-" * len(header))
    for r in results:
        ci = f"[{r['auc_ci95'][0]:.2f}, {r['auc_ci95'][1]:.2f}]"
        if "gains_vs_baseline" in r:
            delta = f"+{r['gains_vs_baseline']}/-{r['losses_vs_baseline']}"
            p = f"{r['sign_test_p']:.3f}"
        else:
            delta, p = "-", "-"
        print(
            f"{r['method']:<28}{r['auc']:>7.3f}{ci:>16}{r['d_prime']:>9.2f}"
            f"{r['paired_accuracy']:>7.0%}{delta:>13}{p:>8}"
        )
        if r is base:
            print("-" * len(header))

    # A one-sentence text is scored identically by both approaches, so those
    # pairs dilute the contrast. Rescore on the pairs where both versions are
    # genuinely multi-sentence: same folds (each was fit on all other pairs),
    # just fewer held-out pairs entering the metric.
    subset = [
        i for i in range(n) if len(sents[i][0]) >= 3 and len(sents[i][1]) >= 3
    ]
    print(
        f"\nMulti-sentence subset: {len(subset)}/{n} pairs where both versions "
        "have 3+ sentences (same folds, metrics over these pairs only)"
    )
    sub_header = f"{'method':<28}{'AUC':>7}{'d-prime':>9}{'paired':>8}"
    print(sub_header)
    print("-" * len(sub_header))
    subset_results = []
    for r in results:
        h = [r["human_scores"][i] for i in subset]
        a = [r["ai_scores"][i] for i in subset]
        row = {
            "method": r["method"],
            "auc": roc_auc(h, a),
            "d_prime": d_prime(h, a),
            "paired_accuracy": sum(x > y for x, y in zip(h, a)) / len(h),
        }
        subset_results.append(row)
    for row in sorted(subset_results, key=lambda x: -x["auc"])[:8]:
        print(
            f"{row['method']:<28}{row['auc']:>7.3f}{row['d_prime']:>9.2f}"
            f"{row['paired_accuracy']:>7.0%}"
        )
    whole_sub = next(r for r in subset_results if r["method"].startswith("whole-text"))
    print(f"(whole-text on this subset: {whole_sub['auc']:.3f})")

    best = max(results[1:], key=lambda r: r["auc"])
    print(
        f"\nBaseline AUC {base['auc']:.3f}; best sentence-level "
        f"{best['method']} at {best['auc']:.3f} "
        f"(+{best['gains_vs_baseline']}/-{best['losses_vs_baseline']} "
        f"comparisons, sign-test p={best['sign_test_p']:.3f}). "
        f"One flipped comparison is {1 / (n * n):.3f} AUC."
    )

    RESULTS_PATH.write_text(
        json.dumps(
            {
                "model": MODEL,
                "dim": DIM,
                "source": source,
                "n_pairs": n,
                "n_sentences": sum(counts),
                "protocol": "leave-one-pair-out (document level)",
                "bootstrap_rounds": BOOTSTRAP_ROUNDS,
                "results": [
                    {k: v for k, v in r.items() if k != "outcomes"} for r in results
                ],
            },
            indent=2,
        )
    )
    print(f"Saved to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
