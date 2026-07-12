"""Orchestrate protocol generation and data access helpers."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from fueldesk.db.models import CheckIn, FoodItem, MealPlan, Profile, Targets, WorkoutPlan
from fueldesk.domain.adjust import suggest_adjustments
from fueldesk.domain.meal_plan import day_totals, generate_meal_week, swap_meal_item
from fueldesk.domain.targets import compute_targets
from fueldesk.domain.workout_plan import generate_workout_week


def week_start_for(today: date | None = None) -> date:
    d = today or date.today()
    return d - timedelta(days=d.weekday())  # Monday


def get_profile(session: Session) -> Profile | None:
    return session.scalar(select(Profile).order_by(Profile.id.asc()).limit(1))


def get_latest_targets(session: Session) -> Targets | None:
    return session.scalar(select(Targets).order_by(Targets.id.desc()).limit(1))


def get_latest_workout(session: Session) -> WorkoutPlan | None:
    return session.scalar(select(WorkoutPlan).order_by(WorkoutPlan.id.desc()).limit(1))


def get_latest_meals(session: Session) -> MealPlan | None:
    return session.scalar(select(MealPlan).order_by(MealPlan.id.desc()).limit(1))


def list_checkins(session: Session, limit: int = 60) -> list[CheckIn]:
    rows = session.scalars(
        select(CheckIn).order_by(CheckIn.date.desc(), CheckIn.id.desc()).limit(limit)
    ).all()
    return list(rows)


def list_foods(session: Session) -> list[dict[str, Any]]:
    rows = session.scalars(select(FoodItem).order_by(FoodItem.name)).all()
    return [
        {
            "name": r.name,
            "calories": r.calories,
            "protein": r.protein,
            "carbs": r.carbs,
            "fat": r.fat,
            "tags": r.tags or [],
        }
        for r in rows
    ]


def save_profile(session: Session, data: dict[str, Any]) -> Profile:
    profile = get_profile(session)
    if profile is None:
        profile = Profile()
        session.add(profile)

    profile.sex = data["sex"]
    profile.age = int(data["age"])
    profile.height_cm = float(data["height_cm"])
    profile.weight_kg = float(data["weight_kg"])
    profile.activity_level = data["activity_level"]
    profile.goal = data["goal"]
    profile.diet_flags = data.get("diet_flags") or []
    profile.equipment = data.get("equipment") or ["bodyweight"]
    profile.days_per_week = int(data.get("days_per_week") or 3)
    profile.experience = data.get("experience") or "beginner"
    profile.notes = data.get("notes") or ""
    profile.units = data.get("units") or "metric"
    profile.updated_at = datetime.utcnow()
    session.flush()
    return profile


def generate_protocol(session: Session, profile: Profile | None = None) -> dict[str, Any]:
    """Compute targets + weekly workout + meal plans; persist latest rows."""
    profile = profile or get_profile(session)
    if profile is None:
        raise ValueError("No profile — complete onboarding first.")

    targets_obj = compute_targets(
        sex=profile.sex,  # type: ignore[arg-type]
        age=profile.age,
        height_cm=profile.height_cm,
        weight_kg=profile.weight_kg,
        activity_level=profile.activity_level,
        goal=profile.goal,
    )

    targets = Targets(
        bmr=targets_obj.bmr,
        tdee=targets_obj.tdee,
        calorie_target=targets_obj.calorie_target,
        protein_g=targets_obj.protein_g,
        carbs_g=targets_obj.carbs_g,
        fat_g=targets_obj.fat_g,
        formula_notes=targets_obj.formula_notes,
    )
    session.add(targets)

    seed_key = f"{profile.id}:{profile.sex}:{profile.goal}:{profile.days_per_week}"
    workout_days = generate_workout_week(
        days_per_week=profile.days_per_week,
        equipment=list(profile.equipment or []),
        experience=profile.experience or "beginner",
        goal=profile.goal,
        seed_key=seed_key,
    )
    ws = week_start_for()
    workout = WorkoutPlan(week_start=ws, days=workout_days)
    session.add(workout)

    foods = list_foods(session)
    meal_days = generate_meal_week(
        foods=foods,
        calorie_target=targets_obj.calorie_target,
        protein_g=targets_obj.protein_g,
        carbs_g=targets_obj.carbs_g,
        fat_g=targets_obj.fat_g,
        diet_flags=list(profile.diet_flags or []),
        seed_key=seed_key,
    )
    meals = MealPlan(week_start=ws, days=meal_days)
    session.add(meals)
    session.flush()

    return {
        "targets": targets,
        "workout": workout,
        "meals": meals,
        "profile": profile,
    }


def add_checkin(session: Session, data: dict[str, Any]) -> CheckIn:
    row = CheckIn(
        date=data.get("date") or date.today(),
        weight_kg=data.get("weight_kg"),
        adherence_meals=data.get("adherence_meals"),
        adherence_training=data.get("adherence_training"),
        energy=data.get("energy"),
        notes=data.get("notes") or "",
    )
    session.add(row)
    session.flush()
    return row


def adjustment_suggestions(session: Session) -> list[str]:
    profile = get_profile(session)
    targets = get_latest_targets(session)
    checkins = list_checkins(session, limit=30)
    payload = [
        {
            "date": c.date.isoformat() if c.date else "",
            "weight_kg": c.weight_kg,
            "adherence_meals": c.adherence_meals,
            "adherence_training": c.adherence_training,
            "energy": c.energy,
            "notes": c.notes,
        }
        for c in reversed(checkins)  # oldest first for trend
    ]
    return suggest_adjustments(
        payload,
        goal=(profile.goal if profile else "maintain"),
        current_calories=(targets.calorie_target if targets else None),
    )


def today_index() -> int:
    return date.today().weekday()  # Mon=0


def dashboard_context(session: Session) -> dict[str, Any]:
    profile = get_profile(session)
    targets = get_latest_targets(session)
    workout = get_latest_workout(session)
    meals = get_latest_meals(session)
    checkins = list_checkins(session, limit=14)
    suggestions = adjustment_suggestions(session) if checkins else []

    idx = today_index()
    today_meals = None
    today_workout = None
    meal_day_totals = None
    if meals and meals.days and idx < len(meals.days):
        today_meals = meals.days[idx]
        meal_day_totals = day_totals(today_meals)
    if workout and workout.days and idx < len(workout.days):
        today_workout = workout.days[idx]

    weights = [
        {"date": c.date.isoformat(), "w": c.weight_kg}
        for c in reversed(checkins)
        if c.weight_kg is not None
    ]

    return {
        "profile": profile,
        "targets": targets,
        "workout": workout,
        "meals": meals,
        "checkins": checkins,
        "suggestions": suggestions,
        "today_meals": today_meals,
        "today_workout": today_workout,
        "meal_day_totals": meal_day_totals,
        "weights": weights,
        "day_name": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][idx],
    }


def export_payload(session: Session) -> dict[str, Any]:
    profile = get_profile(session)
    targets = get_latest_targets(session)
    workout = get_latest_workout(session)
    meals = get_latest_meals(session)
    checkins = list_checkins(session, limit=365)

    def profile_dict(p: Profile | None) -> dict[str, Any] | None:
        if not p:
            return None
        return {
            "sex": p.sex,
            "age": p.age,
            "height_cm": p.height_cm,
            "weight_kg": p.weight_kg,
            "activity_level": p.activity_level,
            "goal": p.goal,
            "diet_flags": p.diet_flags,
            "equipment": p.equipment,
            "days_per_week": p.days_per_week,
            "experience": p.experience,
            "notes": p.notes,
            "units": p.units,
        }

    return {
        "app": "fueldesk",
        "version": "0.1.0",
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "disclaimer": "Educational fitness planning only — not medical advice.",
        "profile": profile_dict(profile),
        "targets": (
            {
                "bmr": targets.bmr,
                "tdee": targets.tdee,
                "calorie_target": targets.calorie_target,
                "protein_g": targets.protein_g,
                "carbs_g": targets.carbs_g,
                "fat_g": targets.fat_g,
                "formula_notes": targets.formula_notes,
                "created_at": targets.created_at.isoformat() if targets.created_at else None,
            }
            if targets
            else None
        ),
        "workout_plan": (
            {
                "week_start": workout.week_start.isoformat(),
                "days": workout.days,
            }
            if workout
            else None
        ),
        "meal_plan": (
            {
                "week_start": meals.week_start.isoformat(),
                "days": meals.days,
            }
            if meals
            else None
        ),
        "checkins": [
            {
                "date": c.date.isoformat(),
                "weight_kg": c.weight_kg,
                "adherence_meals": c.adherence_meals,
                "adherence_training": c.adherence_training,
                "energy": c.energy,
                "notes": c.notes,
            }
            for c in checkins
        ],
    }


def perform_food_swap(
    session: Session,
    *,
    day_index: int,
    meal_index: int,
    item_index: int,
) -> MealPlan | None:
    """Cycle an alternative food for one meal item; mutate latest meal plan."""
    meals = get_latest_meals(session)
    profile = get_profile(session)
    if not meals or not meals.days:
        return None
    days = list(meals.days)
    if day_index < 0 or day_index >= len(days):
        return None
    day = dict(days[day_index])
    meal_list = list(day.get("meals") or [])
    if meal_index < 0 or meal_index >= len(meal_list):
        return None
    meal = dict(meal_list[meal_index])
    items = list(meal.get("foods") or [])
    if item_index < 0 or item_index >= len(items):
        return None

    current = items[item_index]
    foods = list_foods(session)
    alt = swap_meal_item(
        foods,
        list(profile.diet_flags or []) if profile else [],
        current.get("name", ""),
        seed=day_index * 31 + meal_index * 7 + item_index + 1,
    )
    if not alt:
        return None

    # Preserve approximate calories of the slot item
    factor = (current.get("calories") or alt["calories"]) / max(alt["calories"], 1)
    factor = min(max(factor, 0.5), 2.5)
    items[item_index] = {
        "name": alt["name"],
        "calories": int(round(alt["calories"] * factor)),
        "protein": round(alt["protein"] * factor, 1),
        "carbs": round(alt["carbs"] * factor, 1),
        "fat": round(alt["fat"] * factor, 1),
        "tags": alt.get("tags", []),
    }
    meal["foods"] = items
    meal["calories"] = sum(i["calories"] for i in items)
    meal["protein"] = round(sum(i["protein"] for i in items), 1)
    meal["carbs"] = round(sum(i["carbs"] for i in items), 1)
    meal["fat"] = round(sum(i["fat"] for i in items), 1)
    meal_list[meal_index] = meal
    day["meals"] = meal_list
    days[day_index] = day
    meals.days = days
    session.add(meals)
    session.flush()
    return meals
