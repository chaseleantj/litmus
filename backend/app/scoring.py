"""Embedding + style-direction logic, ported from compare.py."""

import hashlib
import json
import math
import os
from pathlib import Path

import requests

MODEL = "openai/text-embedding-3-large"
REQUEST_TIMEOUT = 30

# How far apart two texts must be before the difference is worth reporting.
TOO_CLOSE = 0.02
CLEAR = 0.1

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class EmbeddingError(RuntimeError):
    """The embedding provider failed or is unreachable."""


def load_api_key() -> str:
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("OPENROUTER_API_KEY"):
                return line.split("=", 1)[1].strip()
    raise EmbeddingError("No OPENROUTER_API_KEY found (env var or .env)")


def embed(texts: list[str], api_key: str) -> list[list[float]]:
    try:
        res = requests.post(
            "https://openrouter.ai/api/v1/embeddings",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"model": MODEL, "input": texts},
            timeout=REQUEST_TIMEOUT,
        )
        body = res.json()
    except (requests.RequestException, ValueError) as exc:
        raise EmbeddingError(f"Embedding provider unreachable: {exc}") from exc
    if not res.ok:
        raise EmbeddingError(
            body.get("error", {}).get(
                "message", f"The scoring service returned {res.status_code}."
            )
        )
    data = sorted(body["data"], key=lambda d: d["index"])
    return [d["embedding"] for d in data]


def dot(u: list[float], v: list[float]) -> float:
    return sum(x * y for x, y in zip(u, v))


def direction_key(examples: list[tuple[str, str]]) -> str:
    """sha256 of the scoring format, the model, and a canonical serialization
    of all example texts. The format tag invalidates caches from before
    midpoint centering."""
    canonical = json.dumps(
        [{"ai": ai, "human": human} for ai, human in examples],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(
        ("centered-v2\n" + MODEL + "\n" + canonical).encode("utf-8")
    ).hexdigest()


def learn_direction(examples: list[tuple[str, str]], api_key: str) -> dict:
    """The direction that separates human texts from AI texts: the average step
    from an AI text to its human counterpart, scaled to unit length. Points
    toward human, so a higher score means more human sounding.

    Raw projections onto that direction share a large constant offset (all
    embeddings live in a narrow cone), so scores are centered on the midpoint
    between the two class centroids: bias = dot(midpoint, unit). Zero is then
    the actual decision boundary."""
    texts = [t for ai, human in examples for t in (human, ai)]
    vectors = embed(texts, api_key)
    human = vectors[0::2]
    ai = vectors[1::2]

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
    return {"unit": unit, "bias": dot(midpoint, unit)}


def describe(gap: float, identical: bool) -> str:
    if identical:
        return "The two texts are identical."
    size = abs(gap)
    if size < TOO_CLOSE:
        return "Too close to call."
    more_human = "second" if gap > 0 else "first"
    more_ai = "first" if gap > 0 else "second"
    strength = "clearly" if size >= CLEAR else "slightly"
    return f"The {more_ai} text sounds {strength} more AI than the {more_human} text."


def describe_single(score: float) -> str:
    size = abs(score)
    if size < TOO_CLOSE:
        return "Right on the line - hard to tell."
    side = "more human" if score > 0 else "more AI"
    strength = "clearly" if size >= CLEAR else "slightly"
    return f"This text sounds {strength} {side}."


def score_one(text: str, direction: dict, api_key: str) -> dict:
    (v,) = embed([text], api_key)
    score = dot(v, direction["unit"]) - direction["bias"]
    return {"score": score, "summary": describe_single(score)}


def compare(first: str, second: str, direction: dict | None, api_key: str) -> dict:
    if first.strip() == second.strip():
        return {
            "first": 0.0,
            "second": 0.0,
            "gap": 0.0,
            "summary": describe(0.0, identical=True),
        }
    u, v = embed([first, second], api_key)
    score1 = dot(u, direction["unit"]) - direction["bias"]
    score2 = dot(v, direction["unit"]) - direction["bias"]
    gap = score2 - score1
    return {
        "first": score1,
        "second": score2,
        "gap": gap,
        "summary": describe(gap, identical=False),
    }
