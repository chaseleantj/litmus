"""Embedding + style-direction logic."""

import hashlib
import json
import math
import os
import re

import requests

from .paths import REPO_ROOT

MODEL = "openai/text-embedding-3-small"
REQUEST_TIMEOUT = 30


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


def map_key(examples: list[tuple[str, str]], snippet_chars: int) -> str:
    """Cache key for a map payload. The examples alone are not enough: the same
    library laid out with different projection settings, or carrying different
    snippet lengths, is a different picture — and a persisted cache would
    otherwise serve the old one forever. snippet_chars is passed in because the
    payload shape belongs to the API layer (main.SNIPPET_CHARS), not here."""
    return hashlib.sha256(
        "\n".join(
            [
                "map-v1",
                direction_key(examples),
                str(snippet_chars),
                str(MIN_UMAP_POINTS),
                json.dumps(UMAP_PARAMS, sort_keys=True, separators=(",", ":")),
            ]
        ).encode("utf-8")
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


def _pca_2d(vectors: list[list[float]]) -> list[list[float]]:
    """Top-2 principal components via the Gram-matrix trick, pure Python.
    Fine for a personal library (N is small); used when UMAP is unavailable
    or the library is too small for a meaningful neighbor graph."""
    n = len(vectors)
    dims = len(vectors[0])
    mean = [sum(v[d] for v in vectors) / n for d in range(dims)]
    centered = [[v[d] - mean[d] for d in range(dims)] for v in vectors]
    gram = [[dot(a, b) for b in centered] for a in centered]

    def top_eigenvector(matrix: list[list[float]], deflate: list[float] | None) -> list[float]:
        vec = [math.sin(i + 1.0) for i in range(n)]  # deterministic start
        for _ in range(100):
            if deflate is not None:
                proj = dot(vec, deflate)
                vec = [x - proj * y for x, y in zip(vec, deflate)]
            nxt = [dot(row, vec) for row in matrix]
            length = math.hypot(*nxt)
            if length < 1e-12:
                return [0.0] * n
            vec = [x / length for x in nxt]
        return vec

    e1 = top_eigenvector(gram, None)
    e2 = top_eigenvector(gram, e1)
    # Coordinates are the eigenvectors scaled by their singular values.
    s1 = math.sqrt(max(0.0, dot(e1, [dot(row, e1) for row in gram])))
    s2 = math.sqrt(max(0.0, dot(e2, [dot(row, e2) for row in gram])))
    return [[e1[i] * s1, e2[i] * s2] for i in range(n)]


# UMAP needs a neighbor graph that is meaningful; below this many points the
# spectral machinery degenerates and PCA reads better anyway.
MIN_UMAP_POINTS = 8

# The layout knobs, named here rather than at the call site so map_key can hash
# them: a picture computed under different settings must not be served from the
# cache as if nothing changed.
UMAP_PARAMS = {
    # 15 neighbors on a ~30-point library links each text to half the set,
    # so the layout is almost uniform. 5 keeps local pairs and topic groups.
    "n_neighbors": 5,
    # 0.4 kept every dot isolated. 0.1 lets same-pair and same-topic texts sit close.
    "min_dist": 0.1,
    "metric": "cosine",
    "random_state": 42,  # same library -> same picture
}


def project_2d(vectors: list[list[float]]) -> tuple[list[list[float]], str]:
    """2D layout of the embedding vectors, normalized to [0, 1] with the
    aspect ratio preserved. Returns (coords, method) where method names what
    actually ran — "umap" or "pca" — so the UI never mislabels the picture."""
    coords: list[list[float]] | None = None
    method = "pca"
    if len(vectors) >= MIN_UMAP_POINTS:
        try:
            import warnings

            import numpy as np
            from umap import UMAP

            params = dict(UMAP_PARAMS)
            params["n_neighbors"] = min(params["n_neighbors"], len(vectors) - 1)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                raw = UMAP(**params).fit_transform(np.asarray(vectors, dtype=np.float32))
            coords = [[float(x), float(y)] for x, y in raw]
            method = "umap"
        except Exception:
            # Any failure at all, not just a missing dependency: UMAP's numba
            # and spectral-initialization internals throw on inputs a personal
            # library can easily produce (near-duplicate texts, degenerate
            # neighbor graphs). PCA always works, so a picture the user can
            # read beats a 502 telling them the map is broken.
            coords = None
    if coords is None:
        coords = _pca_2d(vectors)

    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    span = max(maxx - minx, maxy - miny)
    # Fit the longer side to [0, 1] and keep the aspect ratio. Stretching each
    # axis on its own made tight UMAP groups look like they filled the canvas.
    if span < 1e-12:
        return [[0.5, 0.5] for _ in coords], method
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    return [[0.5 + (x - cx) / span, 0.5 + (y - cy) / span] for x, y in coords], method


def project_score(vector: list[float], direction: dict) -> float:
    """A text's position on the learned axis: its projection onto the unit
    direction, centered so zero is the boundary between the two classes. The
    one definition of what a score is — the detector and the map read the same
    number off it."""
    return dot(vector, direction["unit"]) - direction["bias"]


def same_text(first: str, second: str) -> bool:
    """Two texts that differ only in surrounding whitespace are the same text:
    they embed identically, so both score the same and the gap between them is
    zero. Callers check this *before* learning a direction — embedding a
    foregone answer would cost a multi-second round-trip to the provider."""
    return first.strip() == second.strip()


# --- Sentence-level reading -------------------------------------------------
# A text's score is, and stays, the projection of its single whole-text
# embedding: backend/experiments/sentence_scoring.py shows that aggregating
# per-sentence scores never beats it (LOO AUC 0.926 whole-text vs 0.918 for the
# best of 19 aggregation rules, and 0.871 for a plain mean). Sentence scores are
# carried alongside it purely so the UI can show where a text leans — see
# docs/sentence-scoring.md, which also records how weakly a single sentence
# predicts its own text (r = 0.60).

# Fragments shorter than this embed unstably, so they join their neighbour.
MIN_SENT_CHARS = 15

# Sentence punctuation, with any closing quotes or brackets counted as part of
# the separator rather than the next sentence.
_SENT_SEP = re.compile(r"(?<=[.!?])[\)\"']*\s+")


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """Character spans of the text's sentences, as offsets into `text`. The one
    owner of the splitting rule — backend/experiments reads it from here, so the
    app and the research numbers describe the same units.

    A text with no split point is a single span, and spans exclude the
    whitespace between sentences so a span's text is exactly what gets
    embedded."""
    spans: list[tuple[int, int]] = []
    pos = 0
    for match in [*_SENT_SEP.finditer(text), None]:
        end = match.start() if match is not None else len(text)
        segment = text[pos:end]
        start = pos + (len(segment) - len(segment.lstrip()))
        stop = end - (len(segment) - len(segment.rstrip()))
        pos = match.end() if match is not None else end
        if stop <= start:
            continue
        if spans and (
            stop - start < MIN_SENT_CHARS
            or spans[-1][1] - spans[-1][0] < MIN_SENT_CHARS
        ):
            spans[-1] = (spans[-1][0], stop)
        else:
            spans.append((start, stop))
    if not spans:
        # Blank texts are rejected at the API boundary; guard anyway.
        stripped = text.strip()
        first = text.find(stripped)
        return [(first, first + len(stripped))]
    return spans


def _utf16_offsets(text: str, spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """The same spans measured in UTF-16 code units, which is how JavaScript
    indexes a string. Converted here, at the boundary, so one emoji in a pasted
    text cannot shift every highlight after it."""

    def units(upto: int) -> int:
        return len(text[:upto].encode("utf-16-le")) // 2

    return [(units(a), units(b)) for a, b in spans]


def _embed_inputs(text: str, spans: list[tuple[int, int]]) -> list[str]:
    """What one text costs to read: the whole text, then its sentences — unless
    it is a single sentence, where tinting the whole text with its own score
    would say nothing the score does not already say, so there is nothing to
    embed and nothing to show."""
    return [text] + ([text[a:b] for a, b in spans] if len(spans) > 1 else [])


def _scored(
    text: str, spans: list[tuple[int, int]], vectors: list[list[float]], direction: dict
) -> dict:
    """One text's reading, from the vectors _embed_inputs asked for: the score
    is the whole-text projection, and the sentences are carried beside it."""
    return {
        "score": project_score(vectors[0], direction),
        "sentences": [
            {"start": a, "end": b, "score": project_score(v, direction)}
            for (a, b), v in zip(_utf16_offsets(text, spans), vectors[1:])
        ],
    }


def score_text(text: str, direction: dict, api_key: str) -> dict:
    """A text's score, plus each of its sentences' scores on the same axis. Both
    come from one embeddings request, so the sentence reading costs a second
    pass over the text's tokens and no extra round trip."""
    spans = sentence_spans(text)
    return _scored(text, spans, embed(_embed_inputs(text, spans), api_key), direction)


def compare(first: str, second: str, direction: dict, api_key: str) -> dict:
    """Both texts read as score_text reads one, in a single request."""
    spans = [sentence_spans(first), sentence_spans(second)]
    inputs = [_embed_inputs(first, spans[0]), _embed_inputs(second, spans[1])]
    vectors = embed(inputs[0] + inputs[1], api_key)
    scored = [
        _scored(first, spans[0], vectors[: len(inputs[0])], direction),
        _scored(second, spans[1], vectors[len(inputs[0]) :], direction),
    ]
    return {
        "first": scored[0],
        "second": scored[1],
        "gap": scored[1]["score"] - scored[0]["score"],
    }
