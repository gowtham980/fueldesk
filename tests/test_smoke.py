"""App smoke tests: routes return 200 after profile + generate."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fueldesk.db.session import reset_engine
from fueldesk.web.app import create_app


@pytest.fixture()
def client(tmp_path: Path):
    db = tmp_path / "test.db"
    reset_engine()
    app = create_app(db_path=str(db))
    with TestClient(app) as c:
        yield c
    reset_engine()


def test_healthz(client: TestClient):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_empty_dashboard(client: TestClient):
    r = client.get("/")
    assert r.status_code == 200
    assert ("Set up your profile" in r.text) or ("Welcome to fueldesk" in r.text) or ("complete profile" in r.text.lower())


def test_profile_generate_and_pages(client: TestClient):
    # Save vegetarian profile with 3 training days
    r = client.post(
        "/profile",
        data={
            "sex": "female",
            "age": "28",
            "height_cm": "165",
            "weight_kg": "62",
            "activity_level": "light",
            "goal": "lose",
            "days_per_week": "3",
            "experience": "beginner",
            "diet_flags": ["vegetarian"],
            "equipment": ["bodyweight", "dumbbells"],
            "notes": "test",
            "units": "metric",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    for path in ("/", "/profile", "/targets", "/meals", "/training", "/checkins"):
        resp = client.get(path)
        assert resp.status_code == 200, path

    # Targets show formula
    t = client.get("/targets")
    assert "Mifflin" in t.text or "BMR" in t.text

    # Training days
    train = client.get("/training")
    assert train.status_code == 200
    assert "3 training day" in train.text

    # Meals should not advertise chicken for vegetarian (seed chicken name)
    meals = client.get("/meals")
    assert meals.status_code == 200
    assert "chicken" not in meals.text.lower()
    assert "beef" not in meals.text.lower()

    # Export
    exp = client.get("/export.json")
    assert exp.status_code == 200
    data = exp.json()
    assert data["app"] == "fueldesk"
    assert data["profile"]["diet_flags"] == ["vegetarian"]
    assert data["targets"]["calorie_target"] > 0
    assert len(data["workout_plan"]["days"]) == 7
    assert len(data["meal_plan"]["days"]) == 7

    # Check-in
    c = client.post(
        "/checkins",
        data={
            "date": "2026-07-12",
            "weight_kg": "62",
            "adherence_meals": "85",
            "adherence_training": "90",
            "energy": "4",
            "notes": "ok",
        },
        follow_redirects=False,
    )
    assert c.status_code in (302, 303)
    ch = client.get("/checkins")
    assert ch.status_code == 200
    assert "2026-07-12" in ch.text

    # Regenerate
    g = client.post("/protocol/generate", follow_redirects=False)
    assert g.status_code in (302, 303)


def test_validation_error(client: TestClient):
    r = client.post(
        "/profile",
        data={
            "sex": "male",
            "age": "5",
            "height_cm": "170",
            "weight_kg": "70",
            "activity_level": "moderate",
            "goal": "maintain",
            "days_per_week": "3",
            "experience": "beginner",
            "units": "metric",
        },
    )
    assert r.status_code == 400
    assert "Age" in r.text
