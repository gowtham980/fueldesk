"""AI assist orchestration: load config, run providers, apply results."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from fueldesk.db.models import Profile, Setting
from fueldesk.providers.base import (
    AIConfig,
    EquipmentEstimate,
    MealEstimate,
    ProfileParseResult,
    get_provider,
    load_ai_config,
)
from fueldesk.services import protocol as svc

SETTING_KEYS = ("ai_provider", "ai_base_url", "ai_model", "ai_api_key")
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def get_settings_map(session: Session) -> dict[str, str]:
    rows = session.scalars(select(Setting)).all()
    return {r.key: (r.value or "") for r in rows}


def get_setting(session: Session, key: str, default: str = "") -> str:
    row = session.get(Setting, key)
    if row is None:
        return default
    return row.value or default


def set_settings(session: Session, values: dict[str, str]) -> None:
    for key, value in values.items():
        if key not in SETTING_KEYS:
            continue
        row = session.get(Setting, key)
        if row is None:
            row = Setting(key=key, value=value)
            session.add(row)
        else:
            row.value = value
    session.flush()


def resolve_ai_config(session: Session) -> AIConfig:
    return load_ai_config(get_settings_map(session))


def parse_profile(session: Session, text: str) -> ProfileParseResult:
    provider = get_provider(resolve_ai_config(session))
    return provider.parse_profile(text)


def estimate_meal(
    session: Session,
    *,
    image_bytes: bytes | None = None,
    filename: str = "",
    caption: str = "",
) -> MealEstimate:
    provider = get_provider(resolve_ai_config(session))
    return provider.estimate_meal(
        image_bytes=image_bytes, filename=filename, caption=caption
    )


def estimate_equipment(
    session: Session,
    *,
    image_bytes: bytes | None = None,
    filename: str = "",
    caption: str = "",
) -> EquipmentEstimate:
    provider = get_provider(resolve_ai_config(session))
    return provider.estimate_equipment(
        image_bytes=image_bytes, filename=filename, caption=caption
    )


def normalize_profile_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Coerce form/AI fields into save_profile shape."""
    diet = data.get("diet_flags") or []
    if isinstance(diet, str):
        diet = [d.strip() for d in diet.split(",") if d.strip()]
    equip = data.get("equipment") or ["bodyweight"]
    if isinstance(equip, str):
        equip = [e.strip() for e in equip.split(",") if e.strip()]
    return {
        "sex": str(data.get("sex") or "male"),
        "age": int(float(data.get("age") or 30)),
        "height_cm": float(data.get("height_cm") or 170),
        "weight_kg": float(data.get("weight_kg") or 70),
        "activity_level": str(data.get("activity_level") or "moderate"),
        "goal": str(data.get("goal") or "maintain"),
        "diet_flags": list(diet),
        "equipment": list(equip) or ["bodyweight"],
        "days_per_week": max(1, min(7, int(float(data.get("days_per_week") or 3)))),
        "experience": str(data.get("experience") or "beginner"),
        "notes": str(data.get("notes") or ""),
        "units": str(data.get("units") or "metric"),
    }


def apply_profile_and_generate(session: Session, data: dict[str, Any]) -> Profile:
    profile = svc.save_profile(session, normalize_profile_fields(data))
    svc.generate_protocol(session, profile)
    return profile


def apply_equipment(session: Session, equipment: list[str], *, regenerate: bool = True) -> Profile:
    profile = svc.get_profile(session)
    if profile is None:
        raise ValueError("No profile — create one first (AI Profile or Profile form).")
    cleaned = [e for e in equipment if e] or ["bodyweight"]
    profile.equipment = cleaned
    session.flush()
    if regenerate:
        svc.generate_protocol(session, profile)
    return profile


def meal_estimate_to_note(estimate: MealEstimate | dict[str, Any]) -> str:
    if isinstance(estimate, MealEstimate):
        d = estimate.as_dict()
    else:
        d = estimate
    lines = ["[AI meal estimate — not medical advice]"]
    for it in d.get("items") or []:
        lines.append(
            f"- {it.get('name')}: {it.get('calories')} kcal | "
            f"P {it.get('protein_g')}g C {it.get('carbs_g')}g F {it.get('fat_g')}g"
        )
    lines.append(
        f"Total ~{d.get('total_calories')} kcal | "
        f"P {d.get('total_protein')}g C {d.get('total_carbs')}g F {d.get('total_fat')}g "
        f"(confidence {d.get('confidence')}, provider {d.get('provider')})"
    )
    return "\n".join(lines)


def append_meal_note_to_checkin(
    session: Session,
    note: str,
    *,
    weight_kg: float | None = None,
) -> None:
    """Create a check-in for today with the meal estimate note (or append if same day)."""
    today = date.today()
    existing = None
    for c in svc.list_checkins(session, limit=5):
        if c.date == today:
            existing = c
            break
    if existing:
        prev = existing.notes or ""
        existing.notes = (prev + "\n\n" + note).strip() if prev else note
        if weight_kg is not None:
            existing.weight_kg = weight_kg
        session.flush()
        return
    svc.add_checkin(
        session,
        {
            "date": today,
            "weight_kg": weight_kg,
            "adherence_meals": None,
            "adherence_training": None,
            "energy": None,
            "notes": note,
        },
    )
