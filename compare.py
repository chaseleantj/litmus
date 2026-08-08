"""Compare the writing style of two texts against a human/AI direction learned
from a training file of paired examples.

Usage:
    python compare.py examples.json "first text" "second text"
    python compare.py examples.json --batch pairs.json

Batch mode reads a JSON list of pairs, each either {"first": ..., "second": ...}
or a 2-element list [first, second], embeds everything in one API call, and
prints per-pair results plus the mean gap.

The learned direction is cached next to the training file (<training_file>.cache.json)
and recomputed only when the training file or the model changes, so repeated calls
cost a single embedding request.

Requires OPENROUTER_API_KEY in a .env file (KEY=value) in the working directory.
"""

import hashlib
import json
import math
import sys
from pathlib import Path

import requests

MODEL = "openai/text-embedding-3-large"
REQUEST_TIMEOUT = 30

# How far apart two texts must be before the difference is worth reporting.
TOO_CLOSE = 0.02
CLEAR = 0.1


def load_api_key(env_path=".env"):
    import os
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    for candidate in (Path(env_path), Path(__file__).parent / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("OPENROUTER_API_KEY"):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("No OPENROUTER_API_KEY found (env var or .env)")


def embed(texts, api_key):
    res = requests.post(
        "https://openrouter.ai/api/v1/embeddings",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": MODEL, "input": texts},
        timeout=REQUEST_TIMEOUT,
    )
    body = res.json()
    if not res.ok:
        message = json.dumps(body)
        if "maximum input length" in message.lower() or "too long" in message.lower() or "context length" in message.lower():
            raise RuntimeError("TOO_LONG")
        raise RuntimeError(body.get("error", {}).get("message", f"The scoring service returned {res.status_code}."))
    data = sorted(body["data"], key=lambda d: d["index"])
    return [d["embedding"] for d in data]


def dot(u, v):
    return sum(x * y for x, y in zip(u, v))


def learn_direction(examples, api_key):
    """The direction that separates human texts from AI texts: the average step
    from an AI text to its human counterpart, scaled to unit length. Points
    toward human, so a higher score means more human sounding."""
    texts = [t for p in examples for t in (p["human"], p["ai"])]
    vectors = embed(texts, api_key)
    human = vectors[0::2]
    ai = vectors[1::2]

    dims = len(human[0])
    direction = [
        sum(h[d] - a[d] for h, a in zip(human, ai)) / len(human)
        for d in range(dims)
    ]
    length = math.hypot(*direction)
    return [x / length for x in direction]


def load_direction(training_file, api_key):
    """learn_direction with a disk cache, invalidated when the training file
    or the model changes."""
    training_path = Path(training_file)
    raw = training_path.read_text(encoding="utf-8")
    digest = hashlib.sha256((MODEL + "\n" + raw).encode("utf-8")).hexdigest()

    cache_path = training_path.with_suffix(training_path.suffix + ".cache.json")
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("hash") == digest:
                return cached["unit"]
        except (json.JSONDecodeError, KeyError):
            pass  # corrupt cache: fall through and rebuild

    unit = learn_direction(json.loads(raw), api_key)
    cache_path.write_text(json.dumps({"hash": digest, "unit": unit}), encoding="utf-8")
    return unit


def describe(gap, identical):
    if identical:
        return "The two texts are identical."
    size = abs(gap)
    if size < TOO_CLOSE:
        return "Too close to call."
    more_human = "second" if gap > 0 else "first"
    more_ai = "first" if gap > 0 else "second"
    strength = "clearly" if size >= CLEAR else "slightly"
    return f"The {more_ai} text sounds {strength} more AI than the {more_human} text."


def compare(first, second, unit, api_key):
    if first.strip() == second.strip():
        return {
            "first": 0.0,
            "second": 0.0,
            "gap": 0.0,
            "summary": describe(0.0, identical=True),
        }
    u, v = embed([first, second], api_key)
    score1 = dot(u, unit)
    score2 = dot(v, unit)
    gap = score2 - score1
    return {
        "first": score1,
        "second": score2,
        "gap": gap,
        "summary": describe(gap, identical=False),
    }


def compare_batch(pairs, unit, api_key):
    """Score a list of (first, second) pairs with a single embedding call."""
    texts = [t for pair in pairs for t in pair]
    vectors = embed(texts, api_key)
    results = []
    for i, (first, second) in enumerate(pairs):
        if first.strip() == second.strip():
            results.append({"first": 0.0, "second": 0.0, "gap": 0.0,
                            "summary": describe(0.0, identical=True)})
            continue
        score1 = dot(vectors[2 * i], unit)
        score2 = dot(vectors[2 * i + 1], unit)
        gap = score2 - score1
        results.append({"first": score1, "second": score2, "gap": gap,
                        "summary": describe(gap, identical=False)})
    mean_gap = sum(r["gap"] for r in results) / len(results)
    return {"pairs": results, "mean_gap": mean_gap}


def main():
    args = sys.argv[1:]
    if len(args) == 3 and args[1] == "--batch":
        training_file, _, pairs_file = args
        api_key = load_api_key()
        unit = load_direction(training_file, api_key)
        raw = json.loads(Path(pairs_file).read_text(encoding="utf-8"))
        pairs = [
            (p["first"], p["second"]) if isinstance(p, dict) else (p[0], p[1])
            for p in raw
        ]
        if not pairs:
            print("Batch file contains no pairs.")
            sys.exit(1)
        result = compare_batch(pairs, unit, api_key)
    elif len(args) == 3:
        training_file, text1, text2 = args
        api_key = load_api_key()
        unit = load_direction(training_file, api_key)
        result = compare(text1, text2, unit, api_key)
    else:
        print("Usage: python compare.py <training_file.json> <text1> <text2>")
        print("       python compare.py <training_file.json> --batch <pairs.json>")
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
