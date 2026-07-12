"""Unit tests for Mifflin-St Jeor targets and macros."""

from __future__ import annotations

import pytest

from fueldesk.domain.targets import (
    ACTIVITY_MULTIPLIERS,
    apply_goal_calories,
    compute_targets,
    macro_split,
    mifflin_st_jeor_bmr,
    tdee_from_bmr,
    validate_profile_ranges,
)


def test_mifflin_male_known_values():
    # 30y male, 180cm, 80kg
    # 10*80 + 6.25*180 - 5*30 + 5 = 800 + 1125 - 150 + 5 = 1780
    bmr = mifflin_st_jeor_bmr(sex="male", age=30, height_cm=180, weight_kg=80)
    assert abs(bmr - 1780.0) < 0.01


def test_mifflin_female_known_values():
    # 28y female, 165cm, 62kg
    # 10*62 + 6.25*165 - 5*28 - 161 = 620 + 1031.25 - 140 - 161 = 1350.25
    bmr = mifflin_st_jeor_bmr(sex="female", age=28, height_cm=165, weight_kg=62)
    assert abs(bmr - 1350.25) < 0.01


def test_tdee_multipliers():
    bmr = 1780.0
    for level, mult in ACTIVITY_MULTIPLIERS.items():
        assert abs(tdee_from_bmr(bmr, level) - bmr * mult) < 0.01


def test_goal_calories_direction():
    tdee = 2500.0
    lose, d_lose = apply_goal_calories(tdee, "lose")
    maintain, d_m = apply_goal_calories(tdee, "maintain")
    gain, d_g = apply_goal_calories(tdee, "gain")
    assert lose < maintain < gain
    assert d_lose < 0 < d_g
    assert d_m == 0.0


def test_macro_split_sums_near_calories():
    p, c, f = macro_split(calorie_target=2000, weight_kg=70, goal="maintain")
    total = p * 4 + c * 4 + f * 9
    assert abs(total - 2000) <= 50  # rounding tolerance
    assert p > 0 and c >= 0 and f >= 25


def test_compute_targets_full_pipeline():
    t = compute_targets(
        sex="female",
        age=28,
        height_cm=165,
        weight_kg=62,
        activity_level="light",
        goal="lose",
    )
    assert t.bmr == 1350.2 or abs(t.bmr - 1350.25) < 0.2
    assert t.calorie_target < t.tdee
    assert t.protein_g == int(round(62 * 2.0))
    assert "Mifflin-St Jeor" in t.formula_notes


def test_validate_profile_ranges():
    assert validate_profile_ranges(age=30, height_cm=170, weight_kg=70) == []
    assert validate_profile_ranges(age=10, height_cm=170, weight_kg=70)
    assert validate_profile_ranges(age=30, height_cm=50, weight_kg=70)
    assert validate_profile_ranges(age=30, height_cm=170, weight_kg=10)


def test_invalid_sex_raises():
    with pytest.raises(ValueError):
        mifflin_st_jeor_bmr(sex="other", age=30, height_cm=170, weight_kg=70)  # type: ignore[arg-type]


def test_lose_vs_gain_calorie_target():
    base = dict(
        sex="male",
        age=30,
        height_cm=180,
        weight_kg=80,
        activity_level="moderate",
    )
    lose = compute_targets(**base, goal="lose")
    gain = compute_targets(**base, goal="gain")
    maintain = compute_targets(**base, goal="maintain")
    assert lose.calorie_target < maintain.calorie_target < gain.calorie_target
