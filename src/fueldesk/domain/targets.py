"""Mifflin-St Jeor BMR / TDEE / macro targets (pure functions).

Educational formulas only — not medical advice.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

Sex = Literal["male", "female"]
Goal = Literal["lose", "maintain", "gain"]
ActivityLevel = Literal[
    "sedentary",
    "light",
    "moderate",
    "active",
    "very_active",
]

# Standard activity multipliers (Harris/Mifflin common practice)
ACTIVITY_MULTIPLIERS: dict[str, float] = {
    "sedentary": 1.2,  # little/no exercise
    "light": 1.375,  # light exercise 1–3 days/week
    "moderate": 1.55,  # moderate 3–5 days/week
    "active": 1.725,  # hard exercise 6–7 days/week
    "very_active": 1.9,  # very hard exercise + physical job
}

# Goal calorie deltas as fraction of TDEE
GOAL_DELTAS: dict[str, float] = {
    "lose": -0.20,  # ~20% deficit
    "maintain": 0.0,
    "gain": 0.12,  # ~12% surplus
}

# Protein g per kg bodyweight by goal
PROTEIN_G_PER_KG: dict[str, float] = {
    "lose": 2.0,
    "maintain": 1.6,
    "gain": 1.8,
}

# Fat floor as fraction of calories
FAT_CALORIE_FRACTION = 0.25


@dataclass(frozen=True)
class MacroTargets:
    bmr: float
    tdee: float
    calorie_target: int
    protein_g: int
    carbs_g: int
    fat_g: int
    activity_multiplier: float
    goal_delta_fraction: float
    formula_notes: str

    def as_dict(self) -> dict:
        return asdict(self)


def validate_profile_ranges(
    *,
    age: int,
    height_cm: float,
    weight_kg: float,
) -> list[str]:
    """Return list of validation error messages (empty if ok)."""
    errors: list[str] = []
    if not (14 <= age <= 100):
        errors.append("Age must be between 14 and 100.")
    if not (100 <= height_cm <= 250):
        errors.append("Height must be between 100 and 250 cm.")
    if not (30 <= weight_kg <= 400):
        errors.append("Weight must be between 30 and 400 kg.")
    return errors


def mifflin_st_jeor_bmr(
    *,
    sex: Sex,
    age: int,
    height_cm: float,
    weight_kg: float,
) -> float:
    """
    Mifflin-St Jeor resting energy expenditure (kcal/day).

    Male:   10*w + 6.25*h - 5*a + 5
    Female: 10*w + 6.25*h - 5*a - 161
    """
    base = (10.0 * weight_kg) + (6.25 * height_cm) - (5.0 * age)
    if sex == "male":
        return base + 5.0
    if sex == "female":
        return base - 161.0
    raise ValueError(f"Unsupported sex: {sex!r}")


def tdee_from_bmr(bmr: float, activity_level: ActivityLevel | str) -> float:
    mult = ACTIVITY_MULTIPLIERS.get(activity_level)
    if mult is None:
        raise ValueError(f"Unknown activity_level: {activity_level!r}")
    return bmr * mult


def apply_goal_calories(tdee: float, goal: Goal | str) -> tuple[int, float]:
    delta = GOAL_DELTAS.get(goal)
    if delta is None:
        raise ValueError(f"Unknown goal: {goal!r}")
    calories = int(round(tdee * (1.0 + delta)))
    # Safety floor for educational tool
    calories = max(calories, 1200 if goal != "gain" else 1500)
    return calories, delta


def macro_split(
    *,
    calorie_target: int,
    weight_kg: float,
    goal: Goal | str,
) -> tuple[int, int, int]:
    """
    Return (protein_g, carbs_g, fat_g).

    Protein from bodyweight heuristic, fat ~25% calories, carbs fill remainder.
    """
    p_per_kg = PROTEIN_G_PER_KG.get(goal, 1.6)
    protein_g = int(round(weight_kg * p_per_kg))
    protein_cals = protein_g * 4

    fat_cals = int(round(calorie_target * FAT_CALORIE_FRACTION))
    fat_g = max(int(round(fat_cals / 9)), 30)

    remaining = calorie_target - protein_cals - (fat_g * 9)
    if remaining < 0:
        # Rebalance: keep protein, shrink fat slightly, carbs low
        fat_g = max(int(round((calorie_target - protein_cals) * 0.4 / 9)), 25)
        remaining = calorie_target - protein_cals - (fat_g * 9)

    carbs_g = max(int(round(remaining / 4)), 0)
    return protein_g, carbs_g, fat_g


def compute_targets(
    *,
    sex: Sex,
    age: int,
    height_cm: float,
    weight_kg: float,
    activity_level: ActivityLevel | str,
    goal: Goal | str,
) -> MacroTargets:
    """Full pipeline: BMR → TDEE → goal calories → macros."""
    errors = validate_profile_ranges(age=age, height_cm=height_cm, weight_kg=weight_kg)
    if errors:
        raise ValueError("; ".join(errors))

    bmr = mifflin_st_jeor_bmr(
        sex=sex, age=age, height_cm=height_cm, weight_kg=weight_kg
    )
    mult = ACTIVITY_MULTIPLIERS[activity_level]
    tdee = tdee_from_bmr(bmr, activity_level)
    calorie_target, delta = apply_goal_calories(tdee, goal)
    protein_g, carbs_g, fat_g = macro_split(
        calorie_target=calorie_target, weight_kg=weight_kg, goal=goal
    )

    sex_const = "+5" if sex == "male" else "−161"
    notes = (
        f"Mifflin-St Jeor BMR = 10×{weight_kg:g}kg + 6.25×{height_cm:g}cm "
        f"− 5×{age}y {sex_const} = {bmr:.1f} kcal. "
        f"TDEE = BMR × {mult} ({activity_level}) = {tdee:.1f} kcal. "
        f"Goal '{goal}' applies {delta:+.0%} → {calorie_target} kcal. "
        f"Macros: protein {PROTEIN_G_PER_KG.get(goal, 1.6):g} g/kg, "
        f"fat ~{int(FAT_CALORIE_FRACTION * 100)}% calories, carbs remainder."
    )

    return MacroTargets(
        bmr=round(bmr, 1),
        tdee=round(tdee, 1),
        calorie_target=calorie_target,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        activity_multiplier=mult,
        goal_delta_fraction=delta,
        formula_notes=notes,
    )
