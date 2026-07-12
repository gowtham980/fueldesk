"""Weekly meal plan generator from seed foods + diet flags + macro budgets."""

from __future__ import annotations

import hashlib
from typing import Any

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

MEAL_SLOTS = [
    ("Breakfast", 0.25),
    ("Lunch", 0.35),
    ("Dinner", 0.30),
    ("Snack", 0.10),
]

# Meat / animal flesh tags used for vegetarian/vegan filters
MEAT_TAGS = {"meat", "poultry", "fish", "seafood"}
ANIMAL_TAGS = MEAT_TAGS | {"dairy", "egg"}
DAIRY_TAGS = {"dairy"}


def filter_foods(
    foods: list[dict[str, Any]],
    diet_flags: list[str] | None,
) -> list[dict[str, Any]]:
    """Filter seed foods by diet flags (vegetarian, vegan, no_dairy, gluten_free)."""
    flags = {f.strip().lower().replace(" ", "_") for f in (diet_flags or [])}
    out: list[dict[str, Any]] = []
    for food in foods:
        tags = {t.lower() for t in food.get("tags", [])}
        if "vegetarian" in flags or "vegan" in flags:
            if tags & MEAT_TAGS:
                continue
        if "vegan" in flags:
            if tags & ANIMAL_TAGS:
                continue
        if "no_dairy" in flags or "dairy_free" in flags:
            if tags & DAIRY_TAGS:
                continue
        if "gluten_free" in flags:
            if "gluten" in tags:
                continue
        out.append(food)
    return out


def _stable_seed(*parts: Any) -> int:
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(h[:8], 16)


def _scale_food(food: dict[str, Any], factor: float) -> dict[str, Any]:
    factor = max(factor, 0.25)
    return {
        "name": food["name"],
        "calories": int(round(food["calories"] * factor)),
        "protein": round(food["protein"] * factor, 1),
        "carbs": round(food["carbs"] * factor, 1),
        "fat": round(food["fat"] * factor, 1),
        "tags": list(food.get("tags", [])),
    }


def _pick_items_for_budget(
    pool: list[dict[str, Any]],
    calorie_budget: float,
    protein_budget: float,
    seed: int,
    n_items: int = 2,
) -> list[dict[str, Any]]:
    """Pick and lightly scale 1–3 foods to approximate calorie budget."""
    if not pool:
        return [
            {
                "name": "Mixed plate (add foods you like)",
                "calories": int(calorie_budget),
                "protein": round(protein_budget, 1),
                "carbs": round(calorie_budget * 0.45 / 4, 1),
                "fat": round(calorie_budget * 0.25 / 9, 1),
                "tags": [],
            }
        ]

    # Prefer higher protein for main slots when budget allows
    ranked = sorted(
        pool,
        key=lambda f: (f.get("protein", 0) / max(f.get("calories", 1), 1), f["name"]),
        reverse=True,
    )
    picks: list[dict[str, Any]] = []
    used: set[str] = set()
    remaining_cal = calorie_budget

    for i in range(n_items):
        candidates = [f for f in ranked if f["name"] not in used]
        if not candidates:
            candidates = ranked
        idx = (seed + i * 11) % len(candidates)
        food = candidates[idx]
        used.add(food["name"])
        # Share of remaining budget
        share = remaining_cal / max(n_items - i, 1)
        base_cal = max(food["calories"], 1)
        factor = share / base_cal
        # Keep factors reasonable (0.5x–2.5x portion)
        factor = min(max(factor, 0.5), 2.5)
        scaled = _scale_food(food, factor)
        picks.append(scaled)
        remaining_cal -= scaled["calories"]

    # If still far under budget, boost largest item
    total = sum(p["calories"] for p in picks)
    if total > 0 and calorie_budget > 0:
        ratio = calorie_budget / total
        if 0.7 <= ratio <= 1.35:
            picks = [_scale_food(p, ratio) for p in picks]

    return picks


def _meal_from_items(
    name: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "name": name,
        "calories": sum(i["calories"] for i in items),
        "protein": round(sum(i["protein"] for i in items), 1),
        "carbs": round(sum(i["carbs"] for i in items), 1),
        "fat": round(sum(i["fat"] for i in items), 1),
        "foods": items,
    }


def generate_meal_week(
    *,
    foods: list[dict[str, Any]],
    calorie_target: int,
    protein_g: int,
    carbs_g: int,
    fat_g: int,
    diet_flags: list[str] | None = None,
    seed_key: str = "",
) -> list[dict[str, Any]]:
    """
    Build 7 days of meals approximating daily calorie/macro targets.

    Returns list of {day, meals[{name,calories,protein,carbs,fat,items[]}]}
    """
    pool = filter_foods(foods, diet_flags)
    # Never unfilter: empty pool keeps placeholders without disallowed tags.
    # (_pick_items_for_budget already returns a neutral "Mixed plate" placeholder.)

    seed = _stable_seed(seed_key, calorie_target, protein_g, sorted(diet_flags or []))
    days: list[dict[str, Any]] = []

    for di, day_name in enumerate(DAY_NAMES):
        meals = []
        for si, (slot_name, frac) in enumerate(MEAL_SLOTS):
            cal_b = calorie_target * frac
            prot_b = protein_g * frac
            n_items = 3 if slot_name in ("Lunch", "Dinner") else 2
            items = _pick_items_for_budget(
                pool,
                cal_b,
                prot_b,
                seed + di * 17 + si * 3,
                n_items=n_items,
            )
            meals.append(_meal_from_items(slot_name, items))

        # Normalize day total closer to calorie_target (± soft)
        day_cal = sum(m["calories"] for m in meals) or 1
        scale = calorie_target / day_cal
        if 0.85 <= scale <= 1.15:
            scaled_meals = []
            for m in meals:
                new_items = [_scale_food(it, scale) for it in m["foods"]]
                scaled_meals.append(_meal_from_items(m["name"], new_items))
            meals = scaled_meals

        days.append({"day": day_name, "meals": meals})

    return days


def day_totals(day: dict[str, Any]) -> dict[str, float]:
    meals = day.get("meals", [])
    return {
        "calories": sum(m.get("calories", 0) for m in meals),
        "protein": round(sum(m.get("protein", 0) for m in meals), 1),
        "carbs": round(sum(m.get("carbs", 0) for m in meals), 1),
        "fat": round(sum(m.get("fat", 0) for m in meals), 1),
    }


def contains_meat(days: list[dict[str, Any]]) -> bool:
    """True if any meal item has meat/poultry/fish tags."""
    for day in days:
        for meal in day.get("meals", []):
            for item in meal.get("foods", []):
                tags = {t.lower() for t in item.get("tags", [])}
                if tags & MEAT_TAGS:
                    return True
    return False


def swap_meal_item(
    foods: list[dict[str, Any]],
    diet_flags: list[str] | None,
    current_name: str,
    seed: int = 0,
) -> dict[str, Any] | None:
    """Return an alternative food different from current_name."""
    pool = filter_foods(foods, diet_flags)
    alts = [f for f in pool if f["name"] != current_name]
    if not alts:
        return None
    idx = seed % len(alts)
    return dict(alts[idx])
