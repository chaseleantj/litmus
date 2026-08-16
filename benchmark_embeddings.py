"""5-fold CV separation benchmark across OpenRouter embedding models.

Separation score = mean held-out (human_score - ai_score) under the same
style-direction classifier used in production (centered unit direction).
Higher is better: humans should land further above the AI side.
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))
from app import scoring  # noqa: E402

# Top models from MTEB / 2026 rankings that are on OpenRouter, plus the two
# the user required (text-embedding-3-small, gemini-embedding-2) and the
# current production baseline (text-embedding-3-large).
MODELS = [
    "qwen/qwen3-embedding-8b",
    "google/gemini-embedding-2",
    "google/gemini-embedding-001",
    "voyageai/voyage-4-large",
    "qwen/qwen3-embedding-4b",
    "voyageai/voyage-4",
    "openai/text-embedding-3-large",
    "perplexity/pplx-embed-v1-4b",
    "baai/bge-m3",
    "openai/text-embedding-3-small",
]

N_FOLDS = 5
REQUEST_TIMEOUT = 120
BATCH_SIZE = 20  # all 10 pairs = 20 texts; one call when the provider allows it


def embed(model: str, texts: list[str], api_key: str) -> list[list[float]]:
    out: list[list[float] | None] = [None] * len(texts)
    for start in range(0, len(texts), BATCH_SIZE):
        chunk = texts[start : start + BATCH_SIZE]
        last_err = None
        for attempt in range(5):
            try:
                res = requests.post(
                    "https://openrouter.ai/api/v1/embeddings",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"model": model, "input": chunk},
                    timeout=REQUEST_TIMEOUT,
                )
                body = res.json()
                if res.status_code == 429:
                    wait = 2 ** attempt
                    print(f"  rate-limited, retry in {wait}s...", flush=True)
                    time.sleep(wait)
                    continue
                if not res.ok:
                    msg = body.get("error", {})
                    if isinstance(msg, dict):
                        msg = msg.get("message", res.text)
                    raise RuntimeError(f"{res.status_code}: {msg}")
                data = sorted(body["data"], key=lambda d: d["index"])
                for i, row in enumerate(data):
                    out[start + i] = row["embedding"]
                break
            except (requests.RequestException, ValueError, RuntimeError) as exc:
                last_err = exc
                wait = 2 ** attempt
                print(f"  embed error ({exc}), retry in {wait}s...", flush=True)
                time.sleep(wait)
        else:
            raise RuntimeError(f"Failed to embed with {model}: {last_err}")
    assert all(v is not None for v in out)
    return out  # type: ignore[return-value]


def learn_direction(
    human_vecs: list[list[float]], ai_vecs: list[list[float]]
) -> dict:
    dims = len(human_vecs[0])
    n = len(human_vecs)
    direction = [
        sum(h[d] - a[d] for h, a in zip(human_vecs, ai_vecs)) / n for d in range(dims)
    ]
    length = math.hypot(*direction)
    if length == 0:
        raise RuntimeError("zero-length direction")
    unit = [x / length for x in direction]
    midpoint = [
        sum(h[d] + a[d] for h, a in zip(human_vecs, ai_vecs)) / (2 * n)
        for d in range(dims)
    ]
    return {"unit": unit, "bias": scoring.dot(midpoint, unit)}


def score(vec: list[float], direction: dict) -> float:
    return scoring.dot(vec, direction["unit"]) - direction["bias"]


def folds(n: int, k: int) -> list[tuple[list[int], list[int]]]:
    """Contiguous k-fold splits. With n=10, k=5 → 8 train / 2 test each fold."""
    assert n % k == 0
    fold_size = n // k
    out = []
    for i in range(k):
        test = list(range(i * fold_size, (i + 1) * fold_size))
        train = [j for j in range(n) if j not in test]
        out.append((train, test))
    return out


def evaluate(model: str, pairs: list[dict], api_key: str) -> dict:
    texts = [t for p in pairs for t in (p["human"], p["ai"])]
    print(f"\n=== {model} ({len(texts)} texts) ===", flush=True)
    t0 = time.time()
    vectors = embed(model, texts, api_key)
    embed_s = time.time() - t0
    humans = vectors[0::2]
    ais = vectors[1::2]
    dims = len(humans[0])

    gaps: list[float] = []
    human_scores: list[float] = []
    ai_scores: list[float] = []
    correct = 0

    for train_idx, test_idx in folds(len(pairs), N_FOLDS):
        direction = learn_direction(
            [humans[i] for i in train_idx], [ais[i] for i in train_idx]
        )
        for i in test_idx:
            hs = score(humans[i], direction)
            as_ = score(ais[i], direction)
            gap = hs - as_
            gaps.append(gap)
            human_scores.append(hs)
            ai_scores.append(as_)
            if gap > 0:
                correct += 1

    mean_gap = sum(gaps) / len(gaps)
    return {
        "model": model,
        "dims": dims,
        "embed_seconds": round(embed_s, 2),
        "mean_separation": mean_gap,
        "min_separation": min(gaps),
        "max_separation": max(gaps),
        "accuracy": correct / len(gaps),
        "n_pairs": len(gaps),
        "gaps": gaps,
        "human_scores": human_scores,
        "ai_scores": ai_scores,
    }


def main() -> None:
    pairs = json.loads((ROOT / "examples.json").read_text(encoding="utf-8"))
    assert len(pairs) == 10, f"expected 10 pairs, got {len(pairs)}"
    api_key = scoring.load_api_key()

    results = []
    failures = []
    for model in MODELS:
        try:
            results.append(evaluate(model, pairs, api_key))
        except Exception as exc:  # noqa: BLE001 — report and continue
            print(f"FAILED {model}: {exc}", flush=True)
            failures.append({"model": model, "error": str(exc)})

    results.sort(key=lambda r: r["mean_separation"], reverse=True)

    print("\n" + "=" * 78)
    print(
        f"{'model':<36} {'dims':>5} {'sep':>8} {'acc':>6} {'min':>8} {'max':>8} {'s':>5}"
    )
    print("-" * 78)
    for r in results:
        print(
            f"{r['model']:<36} {r['dims']:>5} {r['mean_separation']:>8.4f} "
            f"{r['accuracy']:>5.0%} {r['min_separation']:>8.4f} "
            f"{r['max_separation']:>8.4f} {r['embed_seconds']:>5.1f}"
        )
    if failures:
        print("\nFailures:")
        for f in failures:
            print(f"  {f['model']}: {f['error']}")

    out_path = ROOT / "embedding_benchmark.json"
    out_path.write_text(
        json.dumps({"results": results, "failures": failures}, indent=2),
        encoding="utf-8",
    )
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
