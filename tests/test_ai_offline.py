"""Unit tests for offline AI parsers (no network)."""

from __future__ import annotations

from fueldesk.providers.offline import (
    OfflineProvider,
    estimate_equipment_offline,
    estimate_meal_offline,
    parse_profile_text,
)


def test_parse_profile_rich_sentence():
    text = (
        "28F, 165 cm, 62 kg, vegetarian, light office job, want to lose fat, "
        "train 4 days per week with dumbbells at home, beginner"
    )
    result = parse_profile_text(text)
    f = result.fields
    assert result.provider == "offline"
    assert f["sex"] == "female"
    assert f["age"] == 28
    assert f["height_cm"] == 165
    assert f["weight_kg"] == 62
    assert f["goal"] == "lose"
    assert "vegetarian" in f["diet_flags"]
    assert f["days_per_week"] == 4
    assert "dumbbells" in f["equipment"]
    assert result.confidence >= 0.4


def test_parse_profile_imperial_and_gain():
    text = "I'm a 35 year old male, 5 ft 10 in, 180 lbs, bulk with barbell, intermediate, 5 days/week"
    result = parse_profile_text(text)
    f = result.fields
    assert f["sex"] == "male"
    assert f["age"] == 35
    assert abs(f["height_cm"] - 177.8) < 0.2
    assert abs(f["weight_kg"] - 81.6) < 0.5
    assert f["goal"] == "gain"
    assert "barbell" in f["equipment"]
    assert f["days_per_week"] == 5
    assert f["experience"] == "intermediate"


def test_parse_profile_vegan_gluten_free():
    text = "vegan gluten-free woman age 40, 170cm 65kg maintain sedentary bodyweight 3x per week"
    result = parse_profile_text(text)
    f = result.fields
    assert f["sex"] == "female"
    assert "vegan" in f["diet_flags"]
    assert "gluten_free" in f["diet_flags"]
    assert f["goal"] == "maintain"
    assert f["activity_level"] == "sedentary"


def test_parse_empty_low_confidence():
    result = parse_profile_text("")
    assert result.confidence == 0.0
    assert result.fields == {}


def test_meal_estimate_from_caption_keywords():
    est = estimate_meal_offline(caption="grilled chicken rice salad", filename="lunch.jpg")
    names = " ".join(i.name.lower() for i in est.items)
    assert "chicken" in names
    assert est.total_calories > 0
    assert 0 < est.confidence < 0.8
    assert "Estimates only" in est.disclaimer or any("Estimates" in n for n in est.notes)


def test_meal_estimate_generic_fallback():
    est = estimate_meal_offline(image_bytes=b"\x00" * 1000, filename="photo.png")
    assert len(est.items) >= 1
    assert est.confidence <= 0.35
    assert est.total_calories > 0


def test_equipment_caption_parse():
    est = estimate_equipment_offline(caption="rack, bench, dumbbells, pull-up bar")
    assert "dumbbells" in est.equipment
    assert "pullup_bar" in est.equipment or "barbell" in est.equipment
    assert est.confidence > 0


def test_equipment_empty_no_caption():
    est = estimate_equipment_offline(image_bytes=b"abc", filename="img.jpg")
    assert est.equipment == []
    assert est.confidence == 0.0


def test_offline_provider_class():
    p = OfflineProvider()
    r = p.parse_profile("30M 80kg 180cm gain 4 days/week kettlebell")
    assert r.fields["sex"] == "male"
    assert "kettlebell" in r.fields["equipment"]
