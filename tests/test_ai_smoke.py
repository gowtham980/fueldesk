"""Smoke tests for AI routes and apply path (offline)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fueldesk.db.session import reset_engine
from fueldesk.web.app import create_app


@pytest.fixture()
def client(tmp_path: Path):
    db = tmp_path / "test_ai.db"
    reset_engine()
    app = create_app(db_path=str(db))
    with TestClient(app) as c:
        yield c
    reset_engine()


def test_ai_pages_200(client: TestClient):
    for path in ("/ai", "/ai/profile", "/ai/meal", "/ai/equipment", "/settings/ai"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert "not medical" in r.text.lower() or "Educational" in r.text or "Estimates" in r.text or "AI" in r.text


def test_ai_profile_parse_and_apply(client: TestClient):
    r = client.post(
        "/ai/profile",
        data={
            "action": "parse",
            "text": "28F 165cm 62kg vegetarian lose fat light 4 days/week dumbbells beginner",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    page = client.get("/ai/profile")
    assert page.status_code == 200
    assert "Preview" in page.text or "Apply" in page.text
    assert "female" in page.text.lower() or "62" in page.text

    apply = client.post(
        "/ai/profile",
        data={
            "action": "apply",
            "sex": "female",
            "age": "28",
            "height_cm": "165",
            "weight_kg": "62",
            "activity_level": "light",
            "goal": "lose",
            "days_per_week": "4",
            "experience": "beginner",
            "diet_flags": ["vegetarian"],
            "equipment": ["bodyweight", "dumbbells"],
            "notes": "from ai",
        },
        follow_redirects=False,
    )
    assert apply.status_code in (302, 303)

    dash = client.get("/")
    assert dash.status_code == 200
    targets = client.get("/targets")
    assert targets.status_code == 200
    assert "BMR" in targets.text or "kcal" in targets.text.lower()

    exp = client.get("/export.json")
    data = exp.json()
    assert data["version"] == "0.3.1"
    assert data["profile"]["sex"] == "female"
    assert "vegetarian" in data["profile"]["diet_flags"]


def test_ai_meal_caption_and_save_note(client: TestClient):
    # Need a profile for check-in path optional; save note works without
    r = client.post(
        "/ai/meal",
        data={"action": "estimate", "caption": "chicken rice salad"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    page = client.get("/ai/meal")
    assert page.status_code == 200
    assert "Estimate" in page.text or "kcal" in page.text.lower() or "Chicken" in page.text

    save = client.post(
        "/ai/meal",
        data={
            "action": "save_note",
            "item_name": ["Chicken (est.)", "Rice (est.)"],
            "item_calories": ["250", "200"],
            "item_protein": ["35", "4"],
            "item_carbs": ["0", "42"],
            "item_fat": ["10", "1"],
        },
        follow_redirects=False,
    )
    assert save.status_code in (302, 303)
    ch = client.get("/checkins")
    assert ch.status_code == 200
    assert "AI meal estimate" in ch.text or "Chicken" in ch.text


def test_ai_equipment_apply(client: TestClient):
    # Create profile first
    client.post(
        "/profile",
        data={
            "sex": "male",
            "age": "30",
            "height_cm": "180",
            "weight_kg": "80",
            "activity_level": "moderate",
            "goal": "maintain",
            "days_per_week": "3",
            "experience": "beginner",
            "equipment": ["bodyweight"],
            "units": "metric",
        },
        follow_redirects=False,
    )
    r = client.post(
        "/ai/equipment",
        data={"action": "estimate", "caption": "dumbbells kettlebell bands"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    page = client.get("/ai/equipment")
    assert page.status_code == 200

    apply = client.post(
        "/ai/equipment",
        data={
            "action": "apply",
            "equipment": ["dumbbells", "kettlebell", "bands"],
        },
        follow_redirects=False,
    )
    assert apply.status_code in (302, 303)
    exp = client.get("/export.json").json()
    eq = exp["profile"]["equipment"]
    assert "dumbbells" in eq
    assert "kettlebell" in eq


def test_settings_ai_save(client: TestClient):
    r = client.post(
        "/settings/ai",
        data={
            "ai_provider": "offline",
            "ai_base_url": "",
            "ai_model": "",
            "ai_api_key": "",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    page = client.get("/settings/ai")
    assert page.status_code == 200
    assert "Offline" in page.text or "offline" in page.text


def test_healthz_version(client: TestClient):
    r = client.get("/healthz")
    assert r.json()["version"] == "0.3.1"
