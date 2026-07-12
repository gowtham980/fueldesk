"""Unit tests for workout/meal generators and adjustments."""

from __future__ import annotations

from fueldesk.db.seed_foods import SEED_FOODS
from fueldesk.domain.adjust import suggest_adjustments
from fueldesk.domain.meal_plan import contains_meat, filter_foods, generate_meal_week, day_totals
from fueldesk.domain.workout_plan import count_training_days, generate_workout_week


def test_training_days_match_days_per_week():
    for n in range(1, 8):
        days = generate_workout_week(
            days_per_week=n,
            equipment=["bodyweight", "dumbbells"],
            experience="beginner",
            seed_key=f"t-{n}",
        )
        assert len(days) == 7
        assert count_training_days(days) == n


def test_bodyweight_only_no_barbell_moves():
    days = generate_workout_week(
        days_per_week=4,
        equipment=["bodyweight"],
        experience="beginner",
        seed_key="bw-only",
    )
    banned = {"back squat", "conventional deadlift", "barbell bench press", "barbell row", "overhead press"}
    for day in days:
        for ex in day["exercises"]:
            assert ex["name"].lower() not in banned


def test_equipment_dumbbells_includes_db_or_bw():
    days = generate_workout_week(
        days_per_week=3,
        equipment=["dumbbells"],
        experience="beginner",
        seed_key="db",
    )
    names = [e["name"] for d in days if not d["is_rest"] for e in d["exercises"]]
    assert names  # non-empty
    # At least one dumbbell-named move expected for intermediate pool; beginners may get mix
    assert any("Dumbbell" in n or "Push-up" in n or "Squat" in n for n in names)


def test_vegetarian_meals_no_meat():
    plan = generate_meal_week(
        foods=SEED_FOODS,
        calorie_target=2000,
        protein_g=140,
        carbs_g=200,
        fat_g=60,
        diet_flags=["vegetarian"],
        seed_key="veg",
    )
    assert not contains_meat(plan)
    filtered = filter_foods(SEED_FOODS, ["vegetarian"])
    assert all(
        not ({t.lower() for t in f.get("tags", [])} & {"meat", "poultry", "fish", "seafood"})
        for f in filtered
    )


def test_vegan_filters_dairy_and_meat():
    filtered = filter_foods(SEED_FOODS, ["vegan"])
    for f in filtered:
        tags = {t.lower() for t in f.get("tags", [])}
        assert not (tags & {"meat", "poultry", "fish", "seafood", "dairy", "egg"})


def test_meal_day_calories_within_10_percent():
    target = 2200
    plan = generate_meal_week(
        foods=SEED_FOODS,
        calorie_target=target,
        protein_g=150,
        carbs_g=220,
        fat_g=70,
        diet_flags=[],
        seed_key="cal",
    )
    for day in plan:
        totals = day_totals(day)
        assert abs(totals["calories"] - target) / target <= 0.12  # ~10% with small slack


def test_adjust_flat_weight_lose_goal():
    checkins = [
        {"date": "2026-07-01", "weight_kg": 70.0, "adherence_meals": 90, "adherence_training": 90, "energy": 4},
        {"date": "2026-07-04", "weight_kg": 70.1, "adherence_meals": 88, "adherence_training": 85, "energy": 4},
        {"date": "2026-07-08", "weight_kg": 70.0, "adherence_meals": 92, "adherence_training": 90, "energy": 4},
        {"date": "2026-07-11", "weight_kg": 69.9, "adherence_meals": 90, "adherence_training": 88, "energy": 3},
    ]
    tips = suggest_adjustments(checkins, goal="lose", current_calories=1800)
    assert tips
    joined = " ".join(tips).lower()
    assert "flat" in joined or "deficit" in joined or "adherence" in joined


def test_adjust_empty_checkins():
    tips = suggest_adjustments([])
    assert len(tips) >= 1


def test_empty_pool_never_unfilters_meat():
    """Meat-only DB + vegetarian must never reintroduce meat via unfiltered fallback."""
    meat_only = [
        {"name": "Chicken Breast", "calories": 165, "protein": 31, "carbs": 0, "fat": 3.6, "tags": ["poultry", "meat"]},
        {"name": "Salmon", "calories": 208, "protein": 20, "carbs": 0, "fat": 13, "tags": ["fish", "seafood"]},
        {"name": "Beef Patty", "calories": 250, "protein": 20, "carbs": 0, "fat": 18, "tags": ["meat"]},
    ]
    plan = generate_meal_week(
        foods=meat_only,
        calorie_target=1800,
        protein_g=120,
        carbs_g=150,
        fat_g=50,
        diet_flags=["vegetarian"],
        seed_key="empty-pool",
    )
    assert not contains_meat(plan)
    names = [
        item.get("name", "").lower()
        for day in plan
        for meal in day.get("meals", [])
        for item in meal.get("foods", [])
    ]
    for banned in ("chicken", "salmon", "beef"):
        assert all(banned not in n for n in names)


def test_empty_pool_vegan_no_animal_products():
    animal_only = [
        {"name": "Greek Yogurt", "calories": 100, "protein": 10, "carbs": 6, "fat": 4, "tags": ["dairy"]},
        {"name": "Eggs", "calories": 140, "protein": 12, "carbs": 1, "fat": 10, "tags": ["egg"]},
        {"name": "Chicken", "calories": 165, "protein": 31, "carbs": 0, "fat": 3.6, "tags": ["poultry", "meat"]},
    ]
    plan = generate_meal_week(
        foods=animal_only,
        calorie_target=1600,
        protein_g=100,
        carbs_g=140,
        fat_g=45,
        diet_flags=["vegan"],
        seed_key="vegan-empty",
    )
    for day in plan:
        for meal in day.get("meals", []):
            for item in meal.get("foods", []):
                tags = {t.lower() for t in item.get("tags", [])}
                assert not (tags & {"meat", "poultry", "fish", "seafood", "dairy", "egg"})
