"""Embedding + style-direction logic, ported from compare.py."""

import hashlib
import json
import math
import os
import re
from pathlib import Path

import requests

MODEL = "openai/text-embedding-3-small"
REQUEST_TIMEOUT = 30

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class EmbeddingError(RuntimeError):
    """The embedding provider failed or is unreachable."""


class DirectionError(RuntimeError):
    """The examples on file do not define a usable direction."""


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
    rows = body.get("data")
    if not isinstance(rows, list) or len(rows) != len(texts):
        raise EmbeddingError("The scoring service returned an unexpected response.")
    return [d["embedding"] for d in sorted(rows, key=lambda d: d["index"])]


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
    if length == 0.0:
        # Every pair's two versions embed identically (typically because the
        # two texts are the same), so there is no human-vs-AI axis to project
        # onto. Actionable for the user: the fix is to edit the pairs.
        raise DirectionError(
            "Your training pairs don't differ enough to learn from. "
            "Check for pairs whose two versions are the same text."
        )
    unit = [x / length for x in direction]

    midpoint = [
        sum(h[d] + a[d] for h, a in zip(human, ai)) / (2 * len(human))
        for d in range(dims)
    ]
    return {"unit": unit, "bias": dot(midpoint, unit)}


def score_one(text: str, direction: dict, api_key: str) -> dict:
    (v,) = embed([text], api_key)
    return {"score": dot(v, direction["unit"]) - direction["bias"]}


# --- Sentence-level analysis -------------------------------------------------
# Ports of the two granular approaches validated in
# backend/experiments/granular_detection.py, where both matched the whole-text
# baseline at the document level (LOO AUC ~0.82, 100% paired accuracy):
#   proj  = "sent-proj":       each sentence projected onto the production
#           human-AI axis; document score = trimmed mean. Sentence scores share
#           a whole-document offset, so they read as a relative ranking within
#           the text.
#   match = "bertscore-soft":  each sentence's softmax-weighted similarity to
#           the pool of human example sentences minus the AI pool; document
#           score = mean of the 3 most extreme sentences. Zero-centered, so
#           sentence polarity is absolute.
# Keep the constants and math in step with the experiment.

MIN_SENT_CHARS = 15
SOFTMAX_TEMP = 0.05

_SENT_SEP = re.compile(r"(?<=[.!?])[\)\"']*\s+")


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """Character spans of the text's sentences, as offsets into `text`.

    Same splitting rule as the experiment's split_sentences: split after
    sentence punctuation (trailing quotes/parens belong to the separator), and
    merge fragments shorter than MIN_SENT_CHARS into their neighbour, because
    tiny fragments embed unstably. A text with no split points is one span."""
    spans: list[tuple[int, int]] = []
    pos = 0
    for match in [*_SENT_SEP.finditer(text), None]:
        end = match.start() if match is not None else len(text)
        seg = text[pos:end]
        start = pos + (len(seg) - len(seg.lstrip()))
        stop = end - (len(seg) - len(seg.rstrip()))
        pos = match.end() if match is not None else end
        if stop <= start:
            continue
        short = MIN_SENT_CHARS
        if spans and (stop - start < short or spans[-1][1] - spans[-1][0] < short):
            spans[-1] = (spans[-1][0], stop)
        else:
            spans.append((start, stop))
    if not spans:
        # Whitespace-only texts are rejected upstream; guard anyway.
        stripped = text.strip()
        first = text.find(stripped)
        return [(first, first + len(stripped))]
    return spans


def sentence_pools(examples: list[tuple[str, str]], api_key: str) -> dict:
    """Per-side pools of example-sentence embeddings — the reference set for
    the "match" scorer. All sentences of all examples go in one embeddings
    request."""
    ai_sents: list[str] = []
    human_sents: list[str] = []
    for ai, human in examples:
        ai_sents += [ai[a:b] for a, b in sentence_spans(ai)]
        human_sents += [human[a:b] for a, b in sentence_spans(human)]
    vectors = embed(human_sents + ai_sents, api_key)
    return {"human": vectors[: len(human_sents)], "ai": vectors[len(human_sents):]}


def _soft_affinity(v: list[float], pool: list[list[float]]) -> float:
    """Softmax-weighted (T=SOFTMAX_TEMP) average similarity of v to the pool.
    Shifting by the max similarity keeps exp() in range without changing the
    weighted mean."""
    sims = [dot(v, r) for r in pool]
    peak = max(sims)
    weights = [math.exp((s - peak) / SOFTMAX_TEMP) for s in sims]
    return sum(w * s for w, s in zip(weights, sims)) / sum(weights)


def _trimmed_mean(scores: list[float]) -> float:
    """Mean with the single min and max dropped (when n >= 5)."""
    if len(scores) < 5:
        return sum(scores) / len(scores)
    trimmed = sorted(scores)[1:-1]
    return sum(trimmed) / len(trimmed)


def _top3_extreme(scores: list[float]) -> float:
    """Mean of the 3 scores with the largest magnitude (most confident)."""
    top = sorted(scores, key=abs, reverse=True)[:3]
    return sum(top) / len(top)


def analyze(text: str, direction: dict, pools: dict, api_key: str) -> dict:
    """Sentence-level breakdown: each sentence's span and its score under both
    granular approaches, plus each approach's document score."""
    spans = sentence_spans(text)
    vectors = embed([text[a:b] for a, b in spans], api_key)
    proj = [dot(v, direction["unit"]) - direction["bias"] for v in vectors]
    match = [
        _soft_affinity(v, pools["human"]) - _soft_affinity(v, pools["ai"])
        for v in vectors
    ]
    return {
        "sentences": [
            {"start": a, "end": b, "proj": p, "match": m}
            for (a, b), p, m in zip(spans, proj, match)
        ],
        "proj_score": _trimmed_mean(proj),
        "match_score": _top3_extreme(match),
    }


def compare(first: str, second: str, direction: dict | None, api_key: str) -> dict:
    if first.strip() == second.strip():
        return {"first": 0.0, "second": 0.0, "gap": 0.0}
    u, v = embed([first, second], api_key)
    score1 = dot(u, direction["unit"]) - direction["bias"]
    score2 = dot(v, direction["unit"]) - direction["bias"]
    return {"first": score1, "second": score2, "gap": score2 - score1}
