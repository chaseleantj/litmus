"""Which embedding MODEL separates AI vs human text best?

Sibling of embedding_dims.py: same dataset (the 10 seed pairs in
examples.json), same leave-one-pair-out protocol, same metrics (LOO ROC-AUC
primary, d' and paired accuracy secondary), same per-(model, dims) embedding
cache. See embedding_dims.py's docstring for the metric rationale.

Model lineup: every embedding model actually served by OpenRouter's
/v1/embeddings endpoint that we could verify (probed live), covering
general-purpose (OpenAI 3-small/3-large, Gemini) and retrieval-oriented
(Qwen3-Embedding, Voyage, BGE-M3) families. text-embedding-3-large is also
run truncated to 1536 and 768 via the `dimensions` param for a like-for-like
comparison against 3-small. Probed but NOT served by OpenRouter (skipped):
mistralai/mistral-embed, cohere/embed-v4.0, cohere/embed-english-v3.0,
google/text-embedding-004, qwen/qwen3-embedding-0.6b.

Cost column: actual OpenRouter-reported usage cost of embedding the whole
20-text dataset (~1.6k tokens), captured from the API response at fetch time
and stored in the cache's __meta__ block; "cached" if the vectors predate
cost tracking.

Usage: python backend/experiments/embedding_models.py
Needs OPENROUTER_API_KEY (env var or repo .env). Rerunnable; cached runs
make no API calls. Results saved to embedding_models_results.json.
"""

from __future__ import annotations

import json
import time

from embedding_dims import (
    CACHE_PATH,
    EXPERIMENTS_DIR,
    REPO_ROOT,
    evaluate_dim,
    scoring,
)

RESULTS_PATH = EXPERIMENTS_DIR / "embedding_models_results.json"

# (model, dimensions) — None = the model's native size.
MODELS: list[tuple[str, int | None]] = [
    ("openai/text-embedding-3-small", 1536),  # production baseline (native)
    ("openai/text-embedding-3-large", None),  # native 3072
    ("openai/text-embedding-3-large", 1536),
    ("openai/text-embedding-3-large", 768),
    ("google/gemini-embedding-2", None),
    ("google/gemini-embedding-001", None),
    ("qwen/qwen3-embedding-8b", None),
    ("qwen/qwen3-embedding-4b", None),
    ("voyageai/voyage-4-large", None),
    ("baai/bge-m3", None),
]


def main() -> None:
    pairs = [
        (row["ai"], row["human"])
        for row in json.loads((REPO_ROOT / "examples.json").read_text())
    ]
    print(f"Dataset: {len(pairs)} AI/human pairs ({2 * len(pairs)} texts) "
          "from examples.json")
    print("Protocol: leave-one-pair-out; direction learned as in production\n")

    api_key = scoring.load_api_key()
    cache = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}

    results = []
    for model, dim in MODELS:
        had_cache = any(k.startswith(f"{model}|{dim or 'native'}|") for k in cache)
        r = evaluate_dim(pairs, dim, api_key, cache, model=model)
        meta = cache.get("__meta__", {}).get(f"{model}|{dim or 'native'}")
        r["dataset_cost_usd"] = meta["cost"] if meta else None
        r["dataset_tokens"] = meta["tokens"] if meta else None
        results.append(r)
        if not had_cache:
            time.sleep(1)  # be polite between fresh model fetches

    header = (f"{'model':<33} {'dims':>5}  {'LOO ROC-AUC':>11}  {'d-prime':>8}"
              f"  {'paired acc':>10}  {'dataset cost':>12}")
    print(header)
    print("-" * len(header))
    for r in sorted(results, key=lambda r: -r["auc"]):
        cost = (f"${r['dataset_cost_usd']:.6f}"
                if r["dataset_cost_usd"] is not None else "cached")
        print(f"{r['model']:<33} {r['dim']:>5}  {r['auc']:>11.3f}  "
              f"{r['d_prime']:>8.2f}  {r['paired_accuracy']:>10.0%}  {cost:>12}")

    RESULTS_PATH.write_text(json.dumps(
        {"n_pairs": len(pairs), "protocol": "leave-one-pair-out",
         "results": results},
        indent=2,
    ))
    print(f"\nSaved to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
