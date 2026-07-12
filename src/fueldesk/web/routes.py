"""HTTP routes — pages + export."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from fueldesk.db.session import get_engine, get_session_factory
from fueldesk.domain.meal_plan import day_totals
from fueldesk.domain.targets import validate_profile_ranges
from fueldesk.domain.workout_plan import count_training_days
from fueldesk.services import protocol as svc

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

DIET_OPTIONS = [
    ("vegetarian", "Vegetarian"),
    ("vegan", "Vegan"),
    ("no_dairy", "No dairy"),
    ("gluten_free", "Gluten-free"),
]
EQUIPMENT_OPTIONS = [
    ("bodyweight", "Bodyweight"),
    ("dumbbells", "Dumbbells"),
    ("barbell", "Barbell"),
    ("machines", "Machines"),
    ("bands", "Bands"),
    ("kettlebell", "Kettlebell"),
    ("pullup_bar", "Pull-up bar"),
]
ACTIVITY_OPTIONS = [
    ("sedentary", "Sedentary"),
    ("light", "Light"),
    ("moderate", "Moderate"),
    ("active", "Active"),
    ("very_active", "Very active"),
]
GOAL_OPTIONS = [
    ("lose", "Lose fat"),
    ("maintain", "Maintain"),
    ("gain", "Build muscle"),
]


def _db() -> Session:
    factory = get_session_factory(get_engine())
    return factory()


def _flash(request: Request, message: str, category: str = "info") -> None:
    flashes = request.session.get("flashes") or []
    flashes.append({"message": message, "category": category})
    request.session["flashes"] = flashes


def _pop_flashes(request: Request) -> list[dict[str, str]]:
    flashes = request.session.pop("flashes", [])
    return flashes or []


def _base_ctx(request: Request, **extra: Any) -> dict[str, Any]:
    ctx = {
        "request": request,
        "flashes": _pop_flashes(request),
        "profile": extra.get("profile"),
        "nav": [
            ("/", "dashboard", "Dashboard"),
            ("/profile", "profile", "Profile"),
            ("/targets", "targets", "Targets"),
            ("/meals", "meals", "Meals"),
            ("/training", "training", "Training"),
            ("/checkins", "checkins", "Check-ins"),
        ],
        "disclaimer": (
            "Educational fitness planning tool only — not medical advice. "
            "Consult a qualified professional before changing diet or exercise."
        ),
    }
    ctx.update(extra)
    return ctx


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    session = _db()
    try:
        data = svc.dashboard_context(session)
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            _base_ctx(request, page="dashboard", **data),
        )
    finally:
        session.close()


@router.get("/profile", response_class=HTMLResponse)
def profile_get(request: Request) -> HTMLResponse:
    session = _db()
    try:
        profile = svc.get_profile(session)
        return templates.TemplateResponse(
            request,
            "profile.html",
            _base_ctx(
                request,
                page="profile",
                profile=profile,
                diet_options=DIET_OPTIONS,
                equipment_options=EQUIPMENT_OPTIONS,
                activity_options=ACTIVITY_OPTIONS,
                goal_options=GOAL_OPTIONS,
                errors=[],
            ),
        )
    finally:
        session.close()


@router.post("/profile", response_model=None)
async def profile_post(request: Request):
    form = await request.form()
    session = _db()
    try:
        diet_flags = [v for v in form.getlist("diet_flags") if v]
        equipment = [v for v in form.getlist("equipment") if v] or ["bodyweight"]
        try:
            age = int(str(form.get("age") or "0"))
            height_cm = float(str(form.get("height_cm") or "0"))
            weight_kg = float(str(form.get("weight_kg") or "0"))
            days_per_week = int(str(form.get("days_per_week") or "3"))
        except ValueError:
            _flash(request, "Please enter valid numbers for age, height, weight, days.", "error")
            return RedirectResponse("/profile", status_code=303)

        data = {
            "sex": str(form.get("sex") or "male"),
            "age": age,
            "height_cm": height_cm,
            "weight_kg": weight_kg,
            "activity_level": str(form.get("activity_level") or "moderate"),
            "goal": str(form.get("goal") or "maintain"),
            "diet_flags": diet_flags,
            "equipment": equipment,
            "days_per_week": max(1, min(7, days_per_week)),
            "experience": str(form.get("experience") or "beginner"),
            "notes": str(form.get("notes") or ""),
            "units": str(form.get("units") or "metric"),
        }

        errors = validate_profile_ranges(
            age=data["age"], height_cm=data["height_cm"], weight_kg=data["weight_kg"]
        )
        if data["sex"] not in ("male", "female"):
            errors.append("Sex must be male or female.")
        if data["activity_level"] not in dict(ACTIVITY_OPTIONS):
            errors.append("Invalid activity level.")
        if data["goal"] not in dict(GOAL_OPTIONS):
            errors.append("Invalid goal.")

        if errors:
            profile_stub = type("P", (), data)()
            return templates.TemplateResponse(
            request,
            "profile.html",
            _base_ctx(
                    request,
                    page="profile",
                    profile=profile_stub,
                    diet_options=DIET_OPTIONS,
                    equipment_options=EQUIPMENT_OPTIONS,
                    activity_options=ACTIVITY_OPTIONS,
                    goal_options=GOAL_OPTIONS,
                    errors=errors,
                ),
            status_code=400,
        )

        profile = svc.save_profile(session, data)
        try:
            svc.generate_protocol(session, profile)
            session.commit()
            _flash(request, "Profile saved and weekly protocol generated.", "success")
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            _flash(request, f"Profile saved but generate failed: {exc}", "error")
            session2 = _db()
            try:
                svc.save_profile(session2, data)
                session2.commit()
            finally:
                session2.close()
            return RedirectResponse("/profile", status_code=303)

        return RedirectResponse("/", status_code=303)
    finally:
        session.close()


@router.post("/protocol/generate")
def protocol_generate(request: Request) -> RedirectResponse:
    session = _db()
    try:
        profile = svc.get_profile(session)
        if not profile:
            _flash(request, "Set up your profile first.", "error")
            return RedirectResponse("/profile", status_code=303)
        svc.generate_protocol(session, profile)
        session.commit()
        _flash(request, "Protocol regenerated for this week.", "success")
        return RedirectResponse("/", status_code=303)
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        _flash(request, f"Generate failed: {exc}", "error")
        return RedirectResponse("/", status_code=303)
    finally:
        session.close()


@router.get("/targets", response_class=HTMLResponse)
def targets_page(request: Request) -> HTMLResponse:
    session = _db()
    try:
        profile = svc.get_profile(session)
        targets = svc.get_latest_targets(session)
        return templates.TemplateResponse(
            request,
            "targets.html",
            _base_ctx(request, page="targets", profile=profile, targets=targets),
        )
    finally:
        session.close()


@router.get("/meals", response_class=HTMLResponse)
def meals_page(request: Request) -> HTMLResponse:
    session = _db()
    try:
        profile = svc.get_profile(session)
        meals = svc.get_latest_meals(session)
        targets = svc.get_latest_targets(session)
        day_stats = []
        if meals and meals.days:
            for d in meals.days:
                day_stats.append(day_totals(d))
        return templates.TemplateResponse(
            request,
            "meals.html",
            _base_ctx(
                request,
                page="meals",
                profile=profile,
                meals=meals,
                targets=targets,
                day_stats=day_stats,
            ),
        )
    finally:
        session.close()


@router.post("/meals/swap")
async def meals_swap(request: Request) -> RedirectResponse:
    form = await request.form()
    session = _db()
    try:
        day_index = int(str(form.get("day_index") or "0"))
        meal_index = int(str(form.get("meal_index") or "0"))
        item_index = int(str(form.get("item_index") or "0"))
        result = svc.perform_food_swap(
            session,
            day_index=day_index,
            meal_index=meal_index,
            item_index=item_index,
        )
        if result:
            session.commit()
            _flash(request, "Swapped food item.", "success")
        else:
            _flash(request, "Could not swap that item.", "error")
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        _flash(request, f"Swap failed: {exc}", "error")
    finally:
        session.close()
    return RedirectResponse("/meals", status_code=303)


@router.get("/training", response_class=HTMLResponse)
def training_page(request: Request) -> HTMLResponse:
    session = _db()
    try:
        profile = svc.get_profile(session)
        workout = svc.get_latest_workout(session)
        n_train = count_training_days(workout.days) if workout and workout.days else 0
        return templates.TemplateResponse(
            request,
            "training.html",
            _base_ctx(
                request,
                page="training",
                profile=profile,
                workout=workout,
                training_days_count=n_train,
            ),
        )
    finally:
        session.close()


@router.get("/checkins", response_class=HTMLResponse)
def checkins_get(request: Request) -> HTMLResponse:
    session = _db()
    try:
        checkins = svc.list_checkins(session)
        suggestions = svc.adjustment_suggestions(session)
        profile = svc.get_profile(session)
        weights = [
            {"date": c.date.isoformat(), "w": c.weight_kg}
            for c in reversed(checkins)
            if c.weight_kg is not None
        ]
        return templates.TemplateResponse(
            request,
            "checkins.html",
            _base_ctx(
                request,
                page="checkins",
                checkins=checkins,
                suggestions=suggestions,
                profile=profile,
                weights=weights,
                today=date.today().isoformat(),
        ),
        )
    finally:
        session.close()


@router.post("/checkins")
async def checkins_post(request: Request) -> RedirectResponse:
    form = await request.form()
    session = _db()
    try:
        raw_date = str(form.get("date") or date.today().isoformat())
        try:
            d = date.fromisoformat(raw_date)
        except ValueError:
            d = date.today()

        def _opt_float(key: str) -> float | None:
            v = str(form.get(key) or "").strip()
            if not v:
                return None
            return float(v)

        def _opt_int(key: str) -> int | None:
            v = str(form.get(key) or "").strip()
            if not v:
                return None
            return int(v)

        weight = _opt_float("weight_kg")
        adh_m = _opt_int("adherence_meals")
        adh_t = _opt_int("adherence_training")
        energy = _opt_int("energy")

        if adh_m is not None:
            adh_m = max(0, min(100, adh_m))
        if adh_t is not None:
            adh_t = max(0, min(100, adh_t))
        if energy is not None:
            energy = max(1, min(5, energy))

        svc.add_checkin(
            session,
            {
                "date": d,
                "weight_kg": weight,
                "adherence_meals": adh_m,
                "adherence_training": adh_t,
                "energy": energy,
                "notes": str(form.get("notes") or ""),
            },
        )
        session.commit()
        _flash(request, "Check-in saved.", "success")
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        _flash(request, f"Check-in failed: {exc}", "error")
    finally:
        session.close()
    return RedirectResponse("/checkins", status_code=303)


@router.get("/export.json")
def export_json() -> JSONResponse:
    session = _db()
    try:
        payload = svc.export_payload(session)
        return JSONResponse(payload)
    finally:
        session.close()
