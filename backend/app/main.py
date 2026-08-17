"""Litmus backend: examples CRUD + style comparison."""

import json
import threading
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator, model_validator
from sqlalchemy.orm import Session

from . import scoring
from .db import (
    DirectionCache,
    Example,
    MapCache,
    SentencePoolCache,
    SessionLocal,
    init_db,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SEED_FILE = REPO_ROOT / "examples.json"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"

# Scoring needs a direction, and a direction needs at least this many pairs.
# The frontend gates its UI on the same number (frontend/src/lib/library.svelte.ts).
MIN_EXAMPLES = 2

# Upper bound on a single text. The embedding model tops out at 8192 tokens per
# input; this sits well under that so an over-long paste is a clear 422 here
# rather than an opaque provider error two calls later.
MAX_TEXT_CHARS = 20_000


def seed_if_empty() -> None:
    with SessionLocal() as db:
        if db.query(Example).count() > 0 or not SEED_FILE.exists():
            return
        pairs = json.loads(SEED_FILE.read_text(encoding="utf-8"))
        for pair in pairs:
            db.add(Example(ai=pair["ai"], human=pair["human"]))
        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_if_empty()
    yield


app = FastAPI(
    title="Litmus",
    description=(
        "Trains a model to distinguish AI writing from your own, "
        "then teaches a personal AI to write like you."
    ),
    lifespan=lifespan,
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Schemas ---------------------------------------------------------------

# One owner for what counts as a scorable text, shared by every endpoint that
# accepts one.
def valid_text(v: str) -> str:
    if not v or not v.strip():
        raise ValueError("must be a non-empty text")
    if len(v) > MAX_TEXT_CHARS:
        raise ValueError(f"must be at most {MAX_TEXT_CHARS:,} characters")
    return v


class ExampleIn(BaseModel):
    ai: str
    human: str

    @field_validator("ai", "human")
    @classmethod
    def non_empty(cls, v: str) -> str:
        return valid_text(v)

    @model_validator(mode="after")
    def versions_differ(self):
        # Two identical versions contribute a zero step, and a library of only
        # those leaves no direction to learn (scoring.learn_direction).
        if self.ai.strip() == self.human.strip():
            raise ValueError("the AI version and your version must differ")
        return self


class ExampleOut(BaseModel):
    id: int
    ai: str
    human: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("created_at", "updated_at")
    @classmethod
    def stamp_utc(cls, v: datetime) -> datetime:
        # Timestamps are stored naive UTC (db.utcnow); the offset goes back on
        # here so clients parse an instant, not a local wall-clock time.
        return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v


class CompareIn(BaseModel):
    first: str
    second: str

    @field_validator("first", "second")
    @classmethod
    def non_empty(cls, v: str) -> str:
        return valid_text(v)


class CompareOut(BaseModel):
    first: float
    second: float
    gap: float


class ScoreIn(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def non_empty(cls, v: str) -> str:
        return valid_text(v)


class ScoreOut(BaseModel):
    score: float


# Enough of a text for a map tooltip; the full versions live in the library.
SNIPPET_CHARS = 240


class MapPointOut(BaseModel):
    pair_id: int
    role: str  # "ai" | "human"
    snippet: str
    truncated: bool
    score: float
    x: float
    y: float


class MapOut(BaseModel):
    points: list[MapPointOut]
    method: str  # "umap" | "pca" — whichever projection actually ran
    pairs: int


class SentenceOut(BaseModel):
    """One sentence of the analyzed text: character span into the original
    text plus a score from each granular approach."""

    start: int
    end: int
    proj: float
    match: float


class AnalyzeOut(BaseModel):
    sentences: list[SentenceOut]
    proj_score: float
    match_score: float


# --- Examples CRUD ---------------------------------------------------------


def ordered_examples(db: Session) -> list[Example]:
    return db.query(Example).order_by(Example.id).all()


@app.get("/api/examples", response_model=list[ExampleOut])
def list_examples(db: Session = Depends(get_db)):
    return ordered_examples(db)


@app.post("/api/examples", response_model=ExampleOut, status_code=201)
def create_example(body: ExampleIn, db: Session = Depends(get_db)):
    row = Example(ai=body.ai, human=body.human)
    db.add(row)
    db.commit()
    return row


@app.put("/api/examples/{example_id}", response_model=ExampleOut)
def update_example(example_id: int, body: ExampleIn, db: Session = Depends(get_db)):
    row = db.get(Example, example_id)
    if row is None:
        raise HTTPException(404, detail="Example not found")
    row.ai = body.ai
    row.human = body.human
    db.commit()
    return row


@app.delete("/api/examples/{example_id}", status_code=204)
def delete_example(example_id: int, db: Session = Depends(get_db)):
    row = db.get(Example, example_id)
    if row is None:
        raise HTTPException(404, detail="Example not found")
    db.delete(row)
    db.commit()


@app.post("/api/examples/import")
def import_examples(body: list[ExampleIn], db: Session = Depends(get_db)):
    existing = {(r.ai, r.human) for r in db.query(Example).all()}
    imported = 0
    for pair in body:
        key = (pair.ai, pair.human)
        if key in existing:
            continue
        db.add(Example(ai=pair.ai, human=pair.human))
        existing.add(key)
        imported += 1
    db.commit()
    return {"imported": imported, "total": db.query(Example).count()}


# --- Compare ---------------------------------------------------------------


# Learning a direction is a multi-second call that every request would
# otherwise repeat while the first one is still in flight (these endpoints run
# on a threadpool). One at a time: the losers find the cache warm.
_direction_lock = threading.Lock()


def get_direction(db: Session, api_key: str) -> dict:
    """Learned direction ({unit, bias}), cached in the meta table and keyed by
    the current example texts, so any change to examples causes a recompute."""
    pairs = [(r.ai, r.human) for r in ordered_examples(db)]
    key = scoring.direction_key(pairs)
    with _direction_lock:
        cached = db.get(DirectionCache, key)
        if cached is not None:
            return json.loads(cached.unit_json)
        direction = scoring.learn_direction(pairs, api_key)
        db.query(DirectionCache).delete()
        db.add(DirectionCache(key=key, unit_json=json.dumps(direction)))
        db.commit()
        return direction


@contextmanager
def scoring_errors():
    """One mapping from scoring failures to responses: too few or unusable
    pairs are things the user fixes in the library (409), a provider failure
    is not (502)."""
    try:
        yield
    except scoring.DirectionError as exc:
        raise HTTPException(409, detail=str(exc))
    except scoring.EmbeddingError as exc:
        raise HTTPException(502, detail=str(exc))


def require_calibrated(db: Session) -> None:
    if db.query(Example).count() < MIN_EXAMPLES:
        raise HTTPException(409, detail=f"Need at least {MIN_EXAMPLES} examples")


def api_key_and_direction(db: Session) -> tuple[str, dict]:
    require_calibrated(db)
    with scoring_errors():
        api_key = scoring.load_api_key()
        return api_key, get_direction(db, api_key)


@app.post("/api/compare", response_model=CompareOut)
def compare_texts(body: CompareIn, db: Session = Depends(get_db)):
    require_calibrated(db)
    # Identical texts score identically by definition — no direction needed.
    if body.first.strip() == body.second.strip():
        return scoring.compare(body.first, body.second, None, "")
    api_key, direction = api_key_and_direction(db)
    with scoring_errors():
        return scoring.compare(body.first, body.second, direction, api_key)


@app.post("/api/score", response_model=ScoreOut)
def score_text(body: ScoreIn, db: Session = Depends(get_db)):
    api_key, direction = api_key_and_direction(db)
    with scoring_errors():
        return scoring.score_one(body.text, direction, api_key)


# Same rationale as _direction_lock: the map is a multi-second computation
# that concurrent requests would otherwise all repeat.
_map_lock = threading.Lock()


def build_map(db: Session) -> dict:
    """Embed every example text once, score each along the learned axis, and
    lay the embeddings out in 2D. Cached until the library changes."""
    api_key, direction = api_key_and_direction(db)
    rows = ordered_examples(db)
    key = scoring.direction_key([(r.ai, r.human) for r in rows])
    with _map_lock:
        cached = db.get(MapCache, key)
        if cached is not None:
            return json.loads(cached.payload_json)

        texts: list[str] = []
        meta: list[tuple[int, str]] = []  # (pair_id, role), aligned with texts
        for r in rows:
            texts.append(r.ai)
            meta.append((r.id, "ai"))
            texts.append(r.human)
            meta.append((r.id, "human"))

        with scoring_errors():
            vectors = scoring.embed(texts, api_key)
        coords, method = scoring.project_2d(vectors)

        payload = {
            "points": [
                {
                    "pair_id": pair_id,
                    "role": role,
                    "snippet": text[:SNIPPET_CHARS],
                    "truncated": len(text) > SNIPPET_CHARS,
                    "score": scoring.dot(v, direction["unit"]) - direction["bias"],
                    "x": xy[0],
                    "y": xy[1],
                }
                for (pair_id, role), text, v, xy in zip(meta, texts, vectors, coords)
            ],
            "method": method,
            "pairs": len(rows),
        }
        db.query(MapCache).delete()
        db.add(MapCache(key=key, payload_json=json.dumps(payload)))
        db.commit()
        return payload


@app.get("/api/map", response_model=MapOut)
def map_of_examples(db: Session = Depends(get_db)):
    return build_map(db)


# Same rationale as _direction_lock: building the pools embeds every example
# sentence, and concurrent misses would all pay that cost.
_pools_lock = threading.Lock()


def get_pools(db: Session, api_key: str) -> dict:
    """Example-sentence embedding pools ({human, ai}), cached like the
    direction and keyed by the same examples hash, so any library change
    causes a recompute."""
    pairs = [(r.ai, r.human) for r in ordered_examples(db)]
    key = scoring.direction_key(pairs)
    with _pools_lock:
        cached = db.get(SentencePoolCache, key)
        if cached is not None:
            return json.loads(cached.pools_json)
        pools = scoring.sentence_pools(pairs, api_key)
        db.query(SentencePoolCache).delete()
        db.add(SentencePoolCache(key=key, pools_json=json.dumps(pools)))
        db.commit()
        return pools


@app.post("/api/analyze", response_model=AnalyzeOut)
def analyze_text(body: ScoreIn, db: Session = Depends(get_db)):
    """Sentence-level breakdown of one text under both granular approaches
    (see scoring.analyze). Sits beside /api/score rather than inside it so a
    failure here never takes the whole-text score down with it."""
    api_key, direction = api_key_and_direction(db)
    with scoring_errors():
        pools = get_pools(db, api_key)
        return scoring.analyze(body.text, direction, pools, api_key)


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    return {"status": "ok", "examples": db.query(Example).count()}


# --- Static frontend (optional) ---------------------------------------------

if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")

    @app.exception_handler(404)
    async def spa_fallback(request, exc):
        if request.url.path.startswith("/api/"):
            from fastapi.responses import JSONResponse

            return JSONResponse({"detail": exc.detail}, status_code=404)
        from fastapi.responses import FileResponse

        return FileResponse(FRONTEND_DIST / "index.html")
