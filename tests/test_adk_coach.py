"""Offline ADK coach tools + route smoke (no live Gemini)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fueldesk.db.session import reset_engine
from fueldesk.services import adk_coach
from fueldesk.web.app import create_app


@pytest.fixture()
def client(tmp_path: Path):
    db = tmp_path / "test_adk.db"
    reset_engine()
    adk_coach.clear_chat_history("default")
    app = create_app(db_path=str(db))
    with TestClient(app) as c:
        yield c
    reset_engine()
    adk_coach.clear_chat_history("default")


def test_adk_status_shape():
    status = adk_coach.adk_status()
    assert "available" in status
    assert "install_hint" in status
    # available may be True/False depending on env; never raises


def test_offline_tools_profile_and_stage(client: TestClient):
    # Ensure DB session path works via HTTP coach
    r = client.post(
        "/ai/chat",
        data={
            "action": "chat",
            "message": "Parse: 28F, 165cm, 62kg, vegetarian, lose fat, 4 days/week dumbbells",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    page = client.get("/ai")
    assert page.status_code == 200
    assert "Coach" in page.text or "AI" in page.text
    assert "Staged" in page.text or "Apply" in page.text
    assert "female" in page.text.lower() or "62" in page.text


def test_offline_coach_meal_and_targets(client: TestClient):
    # Seed profile for targets later
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
        "/ai/chat",
        data={"action": "chat", "message": "Explain my calories and macros"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    page = client.get("/ai")
    assert page.status_code == 200
    assert "kcal" in page.text.lower() or "targets" in page.text.lower() or "BMR" in page.text

    r2 = client.post(
        "/ai/chat",
        data={"action": "chat", "message": "Estimate meal: chicken rice salad"},
        follow_redirects=False,
    )
    assert r2.status_code in (302, 303)
    page2 = client.get("/ai")
    assert "Meal" in page2.text or "kcal" in page2.text.lower()


def test_apply_staged_profile(client: TestClient):
    client.post(
        "/ai/chat",
        data={
            "action": "chat",
            "message": "Parse: 28F 165cm 62kg vegetarian lose 4 days/week dumbbells beginner",
        },
        follow_redirects=False,
    )
    apply = client.post(
        "/ai/chat",
        data={"action": "apply_staged"},
        follow_redirects=False,
    )
    assert apply.status_code in (302, 303)
    exp = client.get("/export.json").json()
    assert exp["version"] == "0.3.0"
    assert exp["profile"]["sex"] == "female"
    assert exp["targets"]["calorie_target"] > 0


def test_clear_and_discard(client: TestClient):
    client.post(
        "/ai/chat",
        data={"action": "chat", "message": "hello coach"},
        follow_redirects=False,
    )
    client.post(
        "/ai/chat",
        data={"action": "clear"},
        follow_redirects=False,
    )
    page = client.get("/ai")
    assert page.status_code == 200


def test_unit_tool_wrappers_no_db_profile(tmp_path: Path):
    """Direct tool helpers with empty DB."""
    reset_engine()
    app = create_app(db_path=str(tmp_path / "t.db"))
    # grab a session via app context
    from fueldesk.db.session import get_engine, get_session_factory

    factory = get_session_factory(get_engine())
    session = factory()
    try:
        adk_coach.clear_chat_history("unit")
        summary = adk_coach.tool_get_profile_summary(session)
        assert summary["ok"] is False
        parsed = adk_coach.tool_parse_profile_text(
            session, "30M 80kg 180cm gain kettlebell 4 days/week"
        )
        assert parsed["ok"] is True
        assert parsed["fields"]["sex"] == "male"
        staged = adk_coach.tool_stage_profile_update(
            session, '{"sex":"male","age":30,"height_cm":180,"weight_kg":80,"goal":"gain"}',
            session_key="unit",
        )
        assert staged["ok"] is True
        assert adk_coach.get_staged("unit")["kind"] == "profile"
        meal = adk_coach.tool_estimate_meal_from_caption(session, "oatmeal eggs")
        assert meal["ok"] is True
        assert meal["total_calories"] > 0
        eq = adk_coach.tool_estimate_equipment_from_caption(session, "dumbbells bands")
        assert "dumbbells" in eq["equipment"]
        # offline coach turn
        result = adk_coach.coach_chat(
            session, "What equipment do I have set?", session_key="unit2"
        )
        assert result.reply
        assert result.provider in ("offline", "adk")
    finally:
        session.close()
        reset_engine()
        adk_coach.clear_chat_history("unit")
        adk_coach.clear_chat_history("unit2")


@pytest.mark.skipif(adk_coach.ADK_AVAILABLE, reason="ADK installed — import path covered live")
def test_adk_missing_has_hint():
    status = adk_coach.adk_status()
    assert status["available"] is False
    assert "adk" in status["install_hint"].lower()
