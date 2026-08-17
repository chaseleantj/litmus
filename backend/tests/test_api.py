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


def test_compare_provider_failure_is_502(client, monkeypatch):
    from app import scoring

    def boom(texts, api_key):
        raise scoring.EmbeddingError("provider down")

    monkeypatch.setattr(scoring, "embed", boom)
    r = client.post("/api/compare", json={"first": "aaa", "second": "bbb"})
    assert r.status_code == 502
    assert r.json() == {"detail": "provider down"}


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


# --- Map ----------------------------------------------------------------------


def test_map_needs_two_examples(client, fake_embed):
    clear_examples()
    add(client)
    r = client.get("/api/map")
    assert r.status_code == 409
    assert r.json() == {"detail": "Need at least 2 examples"}


def test_map_returns_two_points_per_pair(client, fake_embed):
    pairs = client.get("/api/examples").json()
    r = client.get("/api/map")
    assert r.status_code == 200
    body = r.json()
    assert body["pairs"] == len(pairs)
    assert body["method"] in {"umap", "pca"}
    points = body["points"]
    assert len(points) == 2 * len(pairs)
    for p in points:
        assert p["role"] in {"ai", "human"}
        assert 0.0 <= p["x"] <= 1.0
        assert 0.0 <= p["y"] <= 1.0
        assert isinstance(p["score"], float)
    # Both roles present for every pair.
    by_pair = {(p["pair_id"], p["role"]) for p in points}
    for pair in pairs:
        assert (pair["id"], "ai") in by_pair
        assert (pair["id"], "human") in by_pair


def test_map_scores_match_the_scoring_axis(client, fake_embed):
    """A point's map score is the same number /api/score would give its text —
    the axis view and the detector share one axis by construction."""
    some_pair = client.get("/api/examples").json()[0]
    map_scores = {
        (p["pair_id"], p["role"]): p["score"] for p in client.get("/api/map").json()["points"]
    }
    scored = client.post("/api/score", json={"text": some_pair["human"]}).json()["score"]
    assert abs(map_scores[(some_pair["id"], "human")] - scored) < 1e-9


def test_map_is_cached_until_the_library_changes(client, fake_embed):
    clear_examples()
    add(client, "ai one", "human one")
    e2 = add(client, "ai two", "human two")

    client.get("/api/map")
    calls = fake_embed.calls  # direction + map texts
    client.get("/api/map")
    assert fake_embed.calls == calls  # fully cached

    # Every kind of library change invalidates: add, edit, delete.
    add(client, "a brand new ai text", "a brand new human text")
    client.get("/api/map")
    assert fake_embed.calls > calls
    calls = fake_embed.calls

    client.put(f"/api/examples/{e2['id']}", json={"ai": "ai two EDITED", "human": "human two"})
    client.get("/api/map")
    assert fake_embed.calls > calls
    calls = fake_embed.calls

    client.delete(f"/api/examples/{e2['id']}")
    client.get("/api/map")
    assert fake_embed.calls > calls


def test_map_cache_is_keyed_to_how_the_payload_is_built(client, fake_embed, monkeypatch):
    """The cache outlives the process (SQLite), so the key has to cover more
    than the texts: changing what goes into the payload must not keep serving
    the picture built under the old settings."""
    from app import main

    client.get("/api/map")
    calls = fake_embed.calls
    monkeypatch.setattr(main, "SNIPPET_CHARS", 40)
    client.get("/api/map")
    assert fake_embed.calls > calls


def test_small_library_reports_the_pca_method(client, fake_embed):
    """The UI prints this label, so it has to name what actually ran: too few
    points for a neighbor graph means PCA."""
    from app.scoring import MIN_UMAP_POINTS

    clear_examples()
    add(client, "ai one", "human one")
    add(client, "ai two", "human two")
    body = client.get("/api/map").json()
    assert 2 * body["pairs"] < MIN_UMAP_POINTS
    assert body["method"] == "pca"


def test_map_snippets_are_truncated_and_say_so(client, fake_embed):
    from app.main import SNIPPET_CHARS

    clear_examples()
    long_text = "long human words " * 40
    assert len(long_text) > SNIPPET_CHARS
    add(client, "short ai text", long_text)
    add(client, "another ai text", "another human text")
    points = client.get("/api/map").json()["points"]
    long_point = next(p for p in points if p["truncated"])
    assert long_point["snippet"] == long_text[:SNIPPET_CHARS]
    short_point = next(p for p in points if p["snippet"] == "short ai text")
    assert short_point["truncated"] is False


def test_map_provider_failure_is_502(client, fake_embed, monkeypatch):
    """The failure has to land in build_map's own embed call — with a cold
    direction cache the request never gets that far, so warm it first."""
    from app import scoring

    pairs = len(client.get("/api/examples").json())
    client.post("/api/score", json={"text": "warm the direction cache"})

    failed_on: list[list[str]] = []

    def boom(texts, api_key):
        failed_on.append(texts)
        raise scoring.EmbeddingError("provider down")

    monkeypatch.setattr(scoring, "embed", boom)
    r = client.get("/api/map")
    assert r.status_code == 502
    assert r.json() == {"detail": "provider down"}
    # The one failed call was the map embedding every library text, not
    # direction learning tripping over first.
    assert [len(t) for t in failed_on] == [2 * pairs]


def test_map_projection_failure_is_mapped_not_a_500(client, fake_embed, monkeypatch):
    """project_2d runs inside the same error mapping as the embedding call, so
    a scoring failure there is a response rather than a stack trace."""
    from app import scoring

    def boom(vectors):
        raise scoring.EmbeddingError("provider down")

    monkeypatch.setattr(scoring, "project_2d", boom)
    r = client.get("/api/map")
    assert r.status_code == 502
    assert r.json() == {"detail": "provider down"}


def test_project_2d_umap_and_pca_agree_on_the_contract():
    """Both projection paths return unit-square coordinates for any N,
    including degenerate inputs."""
    from app.scoring import MIN_UMAP_POINTS, project_2d

    # Above the UMAP threshold (umap-learn is installed in this venv).
    import math

    big = [[math.sin(i * 1.7 + d) for d in range(8)] for i in range(MIN_UMAP_POINTS + 4)]
    coords, method = project_2d(big)
    assert method == "umap"
    assert all(0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 for x, y in coords)

    # Below the threshold: PCA, same contract.
    coords, method = project_2d(big[:4])
    assert method == "pca"
    assert all(0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 for x, y in coords)

    # Identical vectors: no extent to normalize — everything centers.
    coords, method = project_2d([[1.0, 2.0]] * 4)
    assert all((x, y) == (0.5, 0.5) for x, y in coords)


def test_project_2d_falls_back_to_pca_when_umap_fails(monkeypatch):
    """UMAP fails at runtime as well as at import time (numba, spectral init).
    A picture from PCA beats an error page."""
    import math

    import umap

    from app.scoring import MIN_UMAP_POINTS, project_2d

    class Exploding:
        def __init__(self, **kwargs):
            raise RuntimeError("numba fell over")

    monkeypatch.setattr(umap, "UMAP", Exploding)
    big = [[math.sin(i * 1.7 + d) for d in range(8)] for i in range(MIN_UMAP_POINTS + 4)]
    coords, method = project_2d(big)
    assert method == "pca"
    assert all(0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 for x, y in coords)
