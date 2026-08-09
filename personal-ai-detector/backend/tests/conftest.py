import os
import sys
from pathlib import Path

import pytest

# Point the app at a per-session temp database before it is imported.
_TMP = Path(__file__).resolve().parent / "_tmp"
_TMP.mkdir(exist_ok=True)
os.environ["APP_DB_PATH"] = str(_TMP / "test.db")
os.environ["OPENROUTER_API_KEY"] = "test-key"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import scoring  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


class FakeEmbedder:
    """Deterministic embeddings; counts calls so tests can assert caching."""

    def __init__(self):
        self.calls = 0

    def __call__(self, texts, api_key):
        self.calls += 1
        return [self.vector(t) for t in texts]

    @staticmethod
    def vector(text):
        h = sum(ord(c) for c in text)
        return [1.0, float(h % 97) / 97.0, float(len(text) % 13)]


@pytest.fixture()
def fake_embed(monkeypatch):
    fake = FakeEmbedder()
    monkeypatch.setattr(scoring, "embed", fake)
    return fake


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:  # lifespan runs: seeds from repo examples.json
        yield c
