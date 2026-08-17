"""How does embedding dimensionality affect AI-vs-human separation quality?

Sweeps text-embedding-3-small over dimensions 1536/2^n for n = 0..5 using the
OpenAI `dimensions` parameter (MRL truncation + renormalization, passed
through by OpenRouter — verified: the API returns native vectors of the
requested size). Dataset: the seed example pairs in examples.json, the same
pairs production learns its style direction from.

Metric (primary): leave-one-pair-out ROC-AUC of the projection onto the
human-AI direction, learned exactly as production does (scoring.py's
average AI->human step, midpoint-centered). Each pair is held out in turn,
the direction is learned from the remaining pairs, and both held-out texts
are scored; AUC is computed over all held-out scores. Rationale:
  - Held-out (LOO) rather than in-sample: with 10 pairs and 1536 dims an
    in-sample direction separates perfectly at every dimension; only
    held-out scores measure generalization.
  - ROC-AUC is rank-based, so it is insensitive to score scale (which
    shifts with dimension after renormalization) and robust to outliers,
    unlike d' which assumes roughly normal classes — a stretch at n=10.
  - Interpretable: probability a random human text outscores a random AI
    text. 1.0 = perfect separation, 0.5 = chance.
Secondary: d' (pooled-SD standardized mean gap) on the same held-out
scores as an effect-size reading, and paired accuracy (fraction of pairs
whose human text outscores its own AI text — the quantity the product
actually shows users).

Usage: python backend/experiments/embedding_dims.py
Needs OPENROUTER_API_KEY (env var or repo .env). Embeddings are cached in
backend/experiments/embedding_cache.json, so reruns make no API calls.
Results are printed and saved to backend/experiments/embedding_dims_results.json.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
import time
from pathlib import Path

import requests

EXPERIMENTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = EXPERIMENTS_DIR.parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))
from app import scoring  # noqa: E402  (reuse MODEL name + key loading)

DIMENSIONS = [1536, 768, 384, 192, 96, 48]
CACHE_PATH = EXPERIMENTS_DIR / "embedding_cache.json"
RESULTS_PATH = EXPERIMENTS_DIR / "embedding_dims_results.json"


def embed_at_dim(
    texts: list[str],
    dim: int | None,
    api_key: str,
    cache: dict,
    model: str = scoring.MODEL,
) -> list[list[float]]:
    """Embed texts with the given model (at `dimensions=dim` unless None,
    meaning the model's native size), cache-first. Actual API cost/tokens
    for each (model, dim) fetch are recorded under the cache's __meta__ key."""
    dim_tag = dim if dim is not None else "native"
    keys = [
        f"{model}|{dim_tag}|{hashlib.sha256(t.encode('utf-8')).hexdigest()}"
        for t in texts
    ]
    missing = [(k, t) for k, t in zip(keys, texts) if k not in cache]
    if missing:
        payload = {"model": model, "input": [t for _, t in missing]}
        if dim is not None:
            payload["dimensions"] = dim
        for attempt in range(5):
            res = requests.post(
                "https://openrouter.ai/api/v1/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
                timeout=120,
            )
            if res.status_code == 429:
                time.sleep(2**attempt)
                continue
            break
        res.raise_for_status()
        body = res.json()
        rows = sorted(body["data"], key=lambda d: d["index"])
        assert len(rows) == len(missing), "embedding count mismatch"
        for (k, _), row in zip(missing, rows):
            vec = row["embedding"]
            assert dim is None or len(vec) == dim, (
                f"asked for {dim} dims, got {len(vec)}"
            )
            cache[k] = vec
        usage = body.get("usage") or {}
        meta = cache.setdefault("__meta__", {})
        slot = meta.setdefault(f"{model}|{dim_tag}", {"tokens": 0, "cost": 0.0})
        slot["tokens"] += usage.get("prompt_tokens", 0)
        slot["cost"] += usage.get("cost", 0.0)
        CACHE_PATH.write_text(json.dumps(cache))
    return [cache[k] for k in keys]


def learn_direction_from_vectors(
    human: list[list[float]], ai: list[list[float]]
) -> tuple[list[float], float]:
    """Same math as scoring.learn_direction, on precomputed vectors."""
    dims = len(human[0])
    direction = [
        sum(h[d] - a[d] for h, a in zip(human, ai)) / len(human) for d in range(dims)
    ]
    length = math.hypot(*direction)
    unit = [x / length for x in direction]
    midpoint = [
        sum(h[d] + a[d] for h, a in zip(human, ai)) / (2 * len(human))
        for d in range(dims)
    ]
    return unit, scoring.dot(midpoint, unit)


def roc_auc(pos: list[float], neg: list[float]) -> float:
    """Mann-Whitney AUC: P(pos > neg), ties count half."""
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def d_prime(pos: list[float], neg: list[float]) -> float:
    def mean(xs):
        return sum(xs) / len(xs)

    def var(xs):
        m = mean(xs)
        return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)

    pooled = math.sqrt((var(pos) + var(neg)) / 2)
    return (mean(pos) - mean(neg)) / pooled if pooled else float("inf")


def evaluate_dim(
    pairs: list[tuple[str, str]],
    dim: int | None,
    api_key: str,
    cache: dict,
    model: str = scoring.MODEL,
) -> dict:
    texts = [t for ai, human in pairs for t in (ai, human)]
    vecs = embed_at_dim(texts, dim, api_key, cache, model=model)
    ai_vecs = vecs[0::2]
    human_vecs = vecs[1::2]

    human_scores, ai_scores, paired_wins = [], [], 0
    for i in range(len(pairs)):
        train_h = [v for j, v in enumerate(human_vecs) if j != i]
        train_a = [v for j, v in enumerate(ai_vecs) if j != i]
        unit, bias = learn_direction_from_vectors(train_h, train_a)
        h_score = scoring.dot(human_vecs[i], unit) - bias
        a_score = scoring.dot(ai_vecs[i], unit) - bias
        human_scores.append(h_score)
        ai_scores.append(a_score)
        paired_wins += h_score > a_score

    return {
        "model": model,
        "dim": len(vecs[0]),
        "auc": roc_auc(human_scores, ai_scores),
        "d_prime": d_prime(human_scores, ai_scores),
        "paired_accuracy": paired_wins / len(pairs),
        "human_scores": human_scores,
        "ai_scores": ai_scores,
    }


def main() -> None:
    pairs = [
        (row["ai"], row["human"])
        for row in json.loads((REPO_ROOT / "examples.json").read_text())
    ]
    print(f"Dataset: {len(pairs)} AI/human pairs ({2 * len(pairs)} texts) "
          f"from examples.json; model {scoring.MODEL}")
    print("Protocol: leave-one-pair-out; direction learned as in production\n")

    api_key = scoring.load_api_key()
    cache = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}

    results = [evaluate_dim(pairs, dim, api_key, cache) for dim in DIMENSIONS]

    header = f"{'dim':>5}  {'LOO ROC-AUC':>11}  {'d-prime':>8}  {'paired acc':>10}"
    print(header)
    print("-" * len(header))
    for r in results:
        print(f"{r['dim']:>5}  {r['auc']:>11.3f}  {r['d_prime']:>8.2f}  "
              f"{r['paired_accuracy']:>10.0%}")

    RESULTS_PATH.write_text(json.dumps(
        {"model": scoring.MODEL, "n_pairs": len(pairs),
         "protocol": "leave-one-pair-out", "results": results},
        indent=2,
    ))
    print(f"\nSaved to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
