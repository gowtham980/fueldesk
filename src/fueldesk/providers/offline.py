"""Deterministic offline heuristics for profile / meal / equipment assist.

Always works with no network and no model. Used as primary offline provider
and as graceful fallback when remote providers fail.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fueldesk.providers.base import (
    KNOWN_EQUIPMENT,
    EquipmentEstimate,
    MealEstimate,
    MealItemEstimate,
    ProfileParseResult,
)

# --- Profile parse helpers -------------------------------------------------

_SEX_PATTERNS = [
    (re.compile(r"\b(female|woman|girl|she/her)\b", re.I), "female"),
    (re.compile(r"\b(male|man|boy|he/him)\b", re.I), "male"),
    (re.compile(r"\b(\d{2})\s*[fF]\b"), "female"),  # 28F
    (re.compile(r"\b(\d{2})\s*[mM]\b"), "male"),  # 30M
]

_AGE_PATTERNS = [
    re.compile(r"\b(\d{1,2})\s*(?:years?\s*old|yo|y/o)\b", re.I),
    re.compile(r"\bage\s*[:=]?\s*(\d{1,2})\b", re.I),
    re.compile(r"\b(\d{2})\s*[fFmM]\b"),  # 28F / 30M
]

_WEIGHT_KG = re.compile(
    r"\b(\d{2,3}(?:\.\d+)?)\s*(?:kg|kgs|kilos?|kilograms?)\b", re.I
)
_WEIGHT_LB = re.compile(
    r"\b(\d{2,3}(?:\.\d+)?)\s*(?:lb|lbs|pounds?)\b", re.I
)
_HEIGHT_CM = re.compile(
    r"\b(\d{2,3}(?:\.\d+)?)\s*(?:cm|centimet(?:er|re)s?)\b", re.I
)
_HEIGHT_FT_IN = re.compile(
    r"\b(\d)\s*(?:ft|foot|feet|'|′)\s*(?:(\d{1,2})\s*(?:in|inch|inches|\"|″)?)?",
    re.I,
)
_HEIGHT_M = re.compile(r"\b(1\.\d{1,2})\s*m(?:eters?)?\b", re.I)

_GOAL_MAP = [
    (re.compile(r"\b(lose\s*fat|fat\s*loss|cut|cutting|deficit|weight\s*loss|slim)\b", re.I), "lose"),
    (re.compile(r"\b(gain|bulk|bulking|build\s*muscle|surplus|mass)\b", re.I), "gain"),
    (re.compile(r"\b(maintain|recomp|recomposition|maintenance)\b", re.I), "maintain"),
]

_ACTIVITY_MAP = [
    (re.compile(r"\b(sedentary|desk\s*job|office\s*job|no\s*exercise)\b", re.I), "sedentary"),
    (re.compile(r"\b(very\s*active|athlete|physical\s*job)\b", re.I), "very_active"),
    (re.compile(r"\b(active|hard\s*training|6[-–]7)\b", re.I), "active"),
    (re.compile(r"\b(light|1[-–]3\s*days)\b", re.I), "light"),
    (re.compile(r"\b(moderate|3[-–]5)\b", re.I), "moderate"),
]

_EXPERIENCE_MAP = [
    (re.compile(r"\b(intermediate|advanced|experienced)\b", re.I), "intermediate"),
    (re.compile(r"\b(beginner|newbie|new\s*to|starting)\b", re.I), "beginner"),
]

_DIET_MAP = [
    (re.compile(r"\bvegan\b", re.I), "vegan"),
    (re.compile(r"\bvegetarian\b", re.I), "vegetarian"),
    (re.compile(r"\b(no\s*dairy|dairy[- ]free|lactose)\b", re.I), "no_dairy"),
    (re.compile(r"\b(gluten[- ]free|celiac|coeliac)\b", re.I), "gluten_free"),
]

_DAYS_PATTERNS = [
    re.compile(r"\b(\d)\s*(?:x|times)?\s*(?:per|/)\s*week\b", re.I),
    re.compile(r"\b(\d)\s*days?\s*(?:per|/|a)\s*week\b", re.I),
    re.compile(r"\btrain(?:ing)?\s*(\d)\s*days?\b", re.I),
]

_EQUIP_KEYWORDS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(bodyweight|calisthenics|no\s*equipment|home\s*body)\b", re.I), "bodyweight"),
    (re.compile(r"\b(dumbbells?|dbs?|free\s*weights?)\b", re.I), "dumbbells"),
    (re.compile(r"\b(barbells?|squat\s*rack|power\s*rack|olympic\s*bar)\b", re.I), "barbell"),
    (re.compile(r"\b(machines?|cable\s*machine|gym\s*machines?|smith)\b", re.I), "machines"),
    (re.compile(r"\b(bands?|resistance\s*bands?|loop\s*bands?)\b", re.I), "bands"),
    (re.compile(r"\b(kettlebells?|kb)\b", re.I), "kettlebell"),
    (re.compile(r"\b(pull[- ]?up\s*bar|chin[- ]?up\s*bar|pullup)\b", re.I), "pullup_bar"),
    (re.compile(r"\b(bench|rack)\b", re.I), "barbell"),
    (re.compile(r"\b(home\s*gym)\b", re.I), "dumbbells"),
]


def _lb_to_kg(lb: float) -> float:
    return round(lb * 0.45359237, 1)


def _ft_in_to_cm(ft: int, inches: int = 0) -> float:
    return round((ft * 12 + inches) * 2.54, 1)


def parse_profile_text(text: str) -> ProfileParseResult:
    """Regex/heuristic profile extraction from free text."""
    raw = (text or "").strip()
    fields: dict[str, Any] = {}
    notes: list[str] = []
    hits = 0

    if not raw:
        return ProfileParseResult(
            fields={},
            confidence=0.0,
            notes=["No text provided."],
            provider="offline",
        )

    for pat, sex in _SEX_PATTERNS:
        if pat.search(raw):
            fields["sex"] = sex
            hits += 1
            break

    for pat in _AGE_PATTERNS:
        m = pat.search(raw)
        if m:
            age = int(m.group(1))
            if 14 <= age <= 100:
                fields["age"] = age
                hits += 1
                break

    m = _WEIGHT_KG.search(raw)
    if m:
        fields["weight_kg"] = float(m.group(1))
        hits += 1
    else:
        m = _WEIGHT_LB.search(raw)
        if m:
            fields["weight_kg"] = _lb_to_kg(float(m.group(1)))
            notes.append(f"Converted {m.group(1)} lb → {fields['weight_kg']} kg.")
            hits += 1

    m = _HEIGHT_CM.search(raw)
    if m:
        fields["height_cm"] = float(m.group(1))
        hits += 1
    else:
        m = _HEIGHT_M.search(raw)
        if m:
            fields["height_cm"] = round(float(m.group(1)) * 100, 1)
            hits += 1
        else:
            m = _HEIGHT_FT_IN.search(raw)
            if m:
                ft = int(m.group(1))
                inches = int(m.group(2) or 0)
                fields["height_cm"] = _ft_in_to_cm(ft, inches)
                notes.append(f"Converted {ft}\'{inches}\" → {fields['height_cm']} cm.")
                hits += 1

    for pat, goal in _GOAL_MAP:
        if pat.search(raw):
            fields["goal"] = goal
            hits += 1
            break

    for pat, act in _ACTIVITY_MAP:
        if pat.search(raw):
            fields["activity_level"] = act
            hits += 1
            break

    for pat, exp in _EXPERIENCE_MAP:
        if pat.search(raw):
            fields["experience"] = exp
            hits += 1
            break

    diet_flags: list[str] = []
    for pat, flag in _DIET_MAP:
        if pat.search(raw):
            diet_flags.append(flag)
            hits += 1
    if "vegan" in diet_flags and "vegetarian" not in diet_flags:
        diet_flags.append("vegetarian")
    if diet_flags:
        fields["diet_flags"] = diet_flags

    for pat in _DAYS_PATTERNS:
        m = pat.search(raw)
        if m:
            days = int(m.group(1))
            if 1 <= days <= 7:
                fields["days_per_week"] = days
                hits += 1
                break

    equip = extract_equipment_keywords(raw)
    if equip:
        fields["equipment"] = equip
        hits += 1

    if "sex" not in fields:
        fields["sex"] = "male"
        notes.append("Sex not detected — defaulted to male (review).")
    if "age" not in fields:
        fields["age"] = 30
        notes.append("Age not detected — defaulted to 30 (review).")
    if "height_cm" not in fields:
        fields["height_cm"] = 170.0
        notes.append("Height not detected — defaulted to 170 cm (review).")
    if "weight_kg" not in fields:
        fields["weight_kg"] = 70.0
        notes.append("Weight not detected — defaulted to 70 kg (review).")
    if "goal" not in fields:
        fields["goal"] = "maintain"
    if "activity_level" not in fields:
        fields["activity_level"] = "moderate"
    if "experience" not in fields:
        fields["experience"] = "beginner"
    if "days_per_week" not in fields:
        fields["days_per_week"] = 3
    if "equipment" not in fields:
        fields["equipment"] = ["bodyweight"]
    if "diet_flags" not in fields:
        fields["diet_flags"] = []
    fields["units"] = "metric"
    fields["notes"] = raw[:500]

    confidence = min(0.95, 0.15 + hits * 0.1)
    if hits < 3:
        confidence = min(confidence, 0.35)
        notes.append("Low signal — please review all fields carefully.")

    return ProfileParseResult(
        fields=fields,
        confidence=round(confidence, 2),
        notes=notes,
        provider="offline",
        raw_text=raw,
    )


def extract_equipment_keywords(text: str) -> list[str]:
    """Pull known equipment tags from free text / caption / filename."""
    found: list[str] = []
    blob = text or ""
    for pat, tag in _EQUIP_KEYWORDS:
        if pat.search(blob) and tag not in found:
            found.append(tag)
    return [e for e in found if e in KNOWN_EQUIPMENT]


# --- Meal estimate helpers -------------------------------------------------

_FOOD_HINTS: list[tuple[re.Pattern[str], MealItemEstimate]] = [
    (re.compile(r"\b(rice|biryani|pilaf)\b", re.I), MealItemEstimate("Rice (est.)", 200, 4, 42, 1)),
    (re.compile(r"\b(chicken|grilled\s*chicken)\b", re.I), MealItemEstimate("Chicken (est.)", 250, 35, 0, 10)),
    (re.compile(r"\b(salad|greens)\b", re.I), MealItemEstimate("Salad (est.)", 120, 4, 12, 6)),
    (re.compile(r"\b(pasta|noodles|spaghetti)\b", re.I), MealItemEstimate("Pasta (est.)", 320, 12, 55, 6)),
    (re.compile(r"\b(burger|sandwich)\b", re.I), MealItemEstimate("Burger/sandwich (est.)", 480, 25, 40, 22)),
    (re.compile(r"\b(pizza)\b", re.I), MealItemEstimate("Pizza slice (est.)", 285, 12, 36, 10)),
    (re.compile(r"\b(egg|omelet|omelette)\b", re.I), MealItemEstimate("Eggs (est.)", 180, 14, 1, 13)),
    (re.compile(r"\b(oatmeal|oats)\b", re.I), MealItemEstimate("Oatmeal (est.)", 220, 8, 38, 5)),
    (re.compile(r"\b(fish|salmon|tuna)\b", re.I), MealItemEstimate("Fish (est.)", 230, 28, 0, 12)),
    (re.compile(r"\b(tofu|tempeh)\b", re.I), MealItemEstimate("Tofu (est.)", 160, 16, 4, 9)),
    (re.compile(r"\b(dal|daal|lentil|curry)\b", re.I), MealItemEstimate("Dal/curry (est.)", 240, 12, 30, 8)),
    (re.compile(r"\b(roti|chapati|naan|bread)\b", re.I), MealItemEstimate("Bread/roti (est.)", 150, 5, 28, 3)),
    (re.compile(r"\b(yogurt|curd|greek)\b", re.I), MealItemEstimate("Yogurt (est.)", 130, 12, 10, 4)),
    (re.compile(r"\b(avocado)\b", re.I), MealItemEstimate("Avocado (est.)", 160, 2, 9, 15)),
    (re.compile(r"\b(steak|beef)\b", re.I), MealItemEstimate("Beef (est.)", 300, 30, 0, 20)),
]


def estimate_meal_offline(
    *,
    image_bytes: bytes | None = None,
    filename: str = "",
    caption: str = "",
) -> MealEstimate:
    """Heuristic meal estimate from filename/caption (+ generic plated fallback)."""
    blob = f"{filename} {caption}".strip()
    items: list[MealItemEstimate] = []
    notes: list[str] = []

    for pat, item in _FOOD_HINTS:
        if pat.search(blob):
            items.append(
                MealItemEstimate(
                    name=item.name,
                    calories=item.calories,
                    protein_g=item.protein_g,
                    carbs_g=item.carbs_g,
                    fat_g=item.fat_g,
                )
            )

    size = len(image_bytes or b"")
    if not items:
        base_cal = 550
        if size > 800_000:
            base_cal = 650
        elif size and size < 80_000:
            base_cal = 450
        items = [
            MealItemEstimate("Plated meal (est.)", base_cal, 28, 55, 20),
            MealItemEstimate("Side / drink (est.)", 80, 1, 12, 2),
        ]
        notes.append(
            "No food keywords found in filename/caption — used generic plated-meal estimate."
        )
        conf = 0.2
    else:
        conf = min(0.55, 0.25 + 0.08 * len(items))
        notes.append("Matched food keywords offline (no vision model).")

    if image_bytes is None and not blob:
        conf = 0.1
        notes.append("No image or caption provided.")
    elif image_bytes:
        notes.append(
            f"Image received ({size // 1024} KB) — offline mode cannot identify plates visually."
        )

    notes.append("Edit quantities before saving. Estimates only — not lab analysis.")

    return MealEstimate(
        items=items,
        confidence=round(conf, 2),
        notes=notes,
        provider="offline",
    )


def estimate_equipment_offline(
    *,
    image_bytes: bytes | None = None,
    filename: str = "",
    caption: str = "",
) -> EquipmentEstimate:
    """Equipment tags from caption + filename keywords."""
    blob = f"{Path(filename).stem.replace('_', ' ').replace('-', ' ')} {caption}".strip()
    equip = extract_equipment_keywords(blob)
    notes: list[str] = []

    if equip:
        conf = min(0.7, 0.3 + 0.1 * len(equip))
        notes.append("Parsed equipment keywords from caption/filename.")
    else:
        conf = 0.0
        notes.append(
            "No equipment detected offline. Add a caption (e.g. 'rack, bench, dumbbells') "
            "or select chips manually."
        )
        if image_bytes:
            notes.append(
                f"Image received ({len(image_bytes) // 1024} KB) — offline mode has no vision."
            )

    return EquipmentEstimate(
        equipment=equip,
        confidence=round(conf, 2),
        notes=notes,
        provider="offline",
    )


class OfflineProvider:
    name = "offline"

    def parse_profile(self, text: str) -> ProfileParseResult:
        return parse_profile_text(text)

    def estimate_meal(
        self,
        *,
        image_bytes: bytes | None = None,
        filename: str = "",
        caption: str = "",
    ) -> MealEstimate:
        return estimate_meal_offline(
            image_bytes=image_bytes, filename=filename, caption=caption
        )

    def estimate_equipment(
        self,
        *,
        image_bytes: bytes | None = None,
        filename: str = "",
        caption: str = "",
    ) -> EquipmentEstimate:
        return estimate_equipment_offline(
            image_bytes=image_bytes, filename=filename, caption=caption
        )
