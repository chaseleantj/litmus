from datetime import datetime

from app.db import Example, SessionLocal


def clear_examples():
    with SessionLocal() as db:
        db.query(Example).delete()
        db.commit()


def add(client, ai="an ai text", human="a human text"):
    r = client.post("/api/examples", json={"ai": ai, "human": human})
    assert r.status_code == 201
    return r.json()


# --- Seeding & health --------------------------------------------------------


def test_startup_seeds_from_examples_json(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["examples"] > 0  # seeded from repo examples.json


# --- CRUD --------------------------------------------------------------------


def test_crud_roundtrip(client):
    clear_examples()
    created = add(client, "robot words", "person words")
    assert created["ai"] == "robot words"
    assert created["human"] == "person words"
    assert set(created) == {"id", "ai", "human", "created_at", "updated_at"}

    r = client.get("/api/examples")
    assert r.status_code == 200
    assert [e["id"] for e in r.json()] == [created["id"]]

    r = client.put(
        f"/api/examples/{created['id']}", json={"ai": "robot v2", "human": "person v2"}
    )
    assert r.status_code == 200
    assert r.json()["ai"] == "robot v2"

    r = client.delete(f"/api/examples/{created['id']}")
    assert r.status_code == 204
    assert client.get("/api/examples").json() == []


def test_missing_id_is_404(client):
    for r in (
        client.put("/api/examples/999999", json={"ai": "a", "human": "b"}),
        client.delete("/api/examples/999999"),
    ):
        assert r.status_code == 404
        assert "detail" in r.json()


def test_empty_texts_rejected(client):
    for payload in ({"ai": "", "human": "x"}, {"ai": "x", "human": "   "}):
        r = client.post("/api/examples", json=payload)
        assert r.status_code == 422
        assert "detail" in r.json()


# --- Import / export ---------------------------------------------------------


def test_import_appends_and_skips_duplicates(client):
    clear_examples()
    add(client, "dup ai", "dup human")
    r = client.post(
        "/api/examples/import",
        json=[
            {"ai": "dup ai", "human": "dup human"},  # exact duplicate -> skipped
            {"ai": "new ai", "human": "new human"},
            {"ai": "new ai", "human": "new human"},  # duplicate within batch
        ],
    )
    assert r.status_code == 200
    assert r.json() == {"imported": 1, "total": 2}


def test_identical_versions_rejected(client):
    """A pair whose two versions match contributes no direction to learn."""
    r = client.post("/api/examples", json={"ai": "same words", "human": " same words "})
    assert r.status_code == 422
    assert "detail" in r.json()


def test_overlong_text_rejected(client):
    from app.main import MAX_TEXT_CHARS

    r = client.post("/api/examples", json={"ai": "x" * (MAX_TEXT_CHARS + 1), "human": "ok"})
    assert r.status_code == 422


def test_timestamps_are_utc_aware(client):
    """Naive UTC in storage, offset-stamped at the edge — otherwise clients
    parse the value as local time and can show the wrong day."""
    created = add(client, "stamp ai", "stamp human")
    parsed = datetime.fromisoformat(created["created_at"])
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0


# --- Compare -----------------------------------------------------------------


def test_compare_needs_two_examples(client, fake_embed):
    clear_examples()
    add(client)
    r = client.post("/api/compare", json={"first": "a", "second": "b"})
    assert r.status_code == 409
    assert r.json() == {"detail": "Need at least 2 examples"}


def test_compare_validation(client, fake_embed):
    r = client.post("/api/compare", json={"first": "", "second": "b"})
    assert r.status_code == 422


def test_compare_identical_short_circuits(client, fake_embed):
    r = client.post("/api/compare", json={"first": " same ", "second": "same"})
    assert r.status_code == 200
    assert r.json() == {"first": 0.0, "second": 0.0, "gap": 0.0}
    assert fake_embed.calls == 0  # no embedding call at all


def test_compare_returns_scores(client, fake_embed):
    r = client.post("/api/compare", json={"first": "hello there", "second": "general kenobi"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"first", "second", "gap"}
    assert abs(body["gap"] - (body["second"] - body["first"])) < 1e-9
    # one call to learn the direction, one for the two compared texts
    assert fake_embed.calls == 2


def test_direction_cache_reused_then_invalidated(client, fake_embed):
    clear_examples()
    add(client, "ai one", "human one")
    e2 = add(client, "ai two", "human two")

    client.post("/api/compare", json={"first": "aaa", "second": "bbb"})
    assert fake_embed.calls == 2  # direction + pair

    client.post("/api/compare", json={"first": "ccc", "second": "ddd"})
    assert fake_embed.calls == 3  # cached direction, only the pair embedded

    # Editing an example changes the cache key -> direction recomputed.
    client.put(f"/api/examples/{e2['id']}", json={"ai": "ai two EDITED", "human": "human two"})
    client.post("/api/compare", json={"first": "eee", "second": "fff"})
    assert fake_embed.calls == 5  # direction again + pair

    # Deleting also invalidates.
    client.delete(f"/api/examples/{e2['id']}")
    add(client, "ai three", "human three")
    client.post("/api/compare", json={"first": "ggg", "second": "hhh"})
    assert fake_embed.calls == 7


# --- Score (single text) -----------------------------------------------------


def test_score_needs_two_examples(client, fake_embed):
    clear_examples()
    add(client)
    r = client.post("/api/score", json={"text": "hello"})
    assert r.status_code == 409
    assert r.json() == {"detail": "Need at least 2 examples"}


def test_score_validation(client, fake_embed):
    r = client.post("/api/score", json={"text": "   "})
    assert r.status_code == 422


def test_score_returns_score(client, fake_embed):
    r = client.post("/api/score", json={"text": "hello there"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"score"}
    assert isinstance(body["score"], float)
    # one call to learn the direction, one for the scored text
    assert fake_embed.calls == 2


def test_scores_are_centered_on_the_class_midpoint(client, fake_embed):
    """With midpoint centering, the mean score of the human training texts is
    the exact negative of the mean score of the AI training texts."""
    pairs = client.get("/api/examples").json()
    human_scores = [
        client.post("/api/score", json={"text": p["human"]}).json()["score"]
        for p in pairs
    ]
    ai_scores = [
        client.post("/api/score", json={"text": p["ai"]}).json()["score"]
        for p in pairs
    ]
    mean_human = sum(human_scores) / len(human_scores)
    mean_ai = sum(ai_scores) / len(ai_scores)
    assert mean_human > 0 > mean_ai
    assert abs(mean_human + mean_ai) < 1e-9


def test_compare_provider_failure_is_502(client, monkeypatch):
    from app import scoring

    def boom(texts, api_key):
        raise scoring.EmbeddingError("provider down")

    monkeypatch.setattr(scoring, "embed", boom)
    r = client.post("/api/compare", json={"first": "aaa", "second": "bbb"})
    assert r.status_code == 502
    assert r.json() == {"detail": "provider down"}


def test_unusable_pairs_are_409(client, fake_embed, monkeypatch):
    """A library that yields a zero direction must be an actionable 409, not a
    ZeroDivisionError 500. Reaching it needs a write that bypasses validation."""
    clear_examples()
    with SessionLocal() as db:
        db.add(Example(ai="identical", human="identical"))
        db.add(Example(ai="also same", human="also same"))
        db.commit()
    r = client.post("/api/score", json={"text": "hello"})
    assert r.status_code == 409
    assert "differ" in r.json()["detail"]
