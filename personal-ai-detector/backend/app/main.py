"""Personal AI Detector backend: examples CRUD + style comparison."""

import json
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from . import scoring
from .db import DirectionCache, Example, SessionLocal, init_db

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SEED_FILE = REPO_ROOT / "examples.json"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


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
    title="Personal AI Detector",
    description=(
        "Trains a model to distinguish AI writing from your own, "
        "then teaches a personal AI to write like you."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Schemas ---------------------------------------------------------------


class ExampleIn(BaseModel):
    ai: str
    human: str

    @field_validator("ai", "human")
    @classmethod
    def non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must be a non-empty text")
        return v


class ExampleOut(BaseModel):
    id: int
    ai: str
    human: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CompareIn(BaseModel):
    first: str
    second: str

    @field_validator("first", "second")
    @classmethod
    def non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must be a non-empty text")
        return v


class CompareOut(BaseModel):
    first: float
    second: float
    gap: float
    summary: str


class ScoreIn(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must be a non-empty text")
        return v


class ScoreOut(BaseModel):
    score: float
    summary: str


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


@app.get("/api/examples/export")
def export_examples(db: Session = Depends(get_db)):
    pairs = [{"ai": r.ai, "human": r.human} for r in ordered_examples(db)]
    return Response(
        content=json.dumps(pairs, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=examples.json"},
    )


# --- Compare ---------------------------------------------------------------


def get_direction(db: Session, api_key: str) -> list[float]:
    """Learned unit direction, cached in the meta table and keyed by the
    current example texts, so any change to examples causes a recompute."""
    pairs = [(r.ai, r.human) for r in ordered_examples(db)]
    key = scoring.direction_key(pairs)
    cached = db.get(DirectionCache, key)
    if cached is not None:
        return json.loads(cached.unit_json)
    unit = scoring.learn_direction(pairs, api_key)
    db.query(DirectionCache).delete()
    db.add(DirectionCache(key=key, unit_json=json.dumps(unit)))
    db.commit()
    return unit


@app.post("/api/compare", response_model=CompareOut)
def compare_texts(body: CompareIn, db: Session = Depends(get_db)):
    if db.query(Example).count() < 2:
        raise HTTPException(409, detail="Need at least 2 examples")
    if body.first.strip() == body.second.strip():
        return scoring.compare(body.first, body.second, [], "")
    try:
        api_key = scoring.load_api_key()
        unit = get_direction(db, api_key)
        return scoring.compare(body.first, body.second, unit, api_key)
    except scoring.EmbeddingError as exc:
        raise HTTPException(502, detail=str(exc))


@app.post("/api/score", response_model=ScoreOut)
def score_text(body: ScoreIn, db: Session = Depends(get_db)):
    if db.query(Example).count() < 2:
        raise HTTPException(409, detail="Need at least 2 examples")
    try:
        api_key = scoring.load_api_key()
        unit = get_direction(db, api_key)
        return scoring.score_one(body.text, unit, api_key)
    except scoring.EmbeddingError as exc:
        raise HTTPException(502, detail=str(exc))


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
