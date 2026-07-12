"""Check-in based adjustment suggestions (educational, not medical)."""

from __future__ import annotations

from typing import Any


def suggest_adjustments(
    checkins: list[dict[str, Any]],
    *,
    goal: str = "maintain",
    current_calories: int | None = None,
) -> list[str]:
    """
    Return human-readable suggestions from recent check-ins.

    checkins: newest-last or newest-first; we sort by date if present.
    Fields: date, weight_kg, adherence_meals, adherence_training, energy, notes
    """
    if not checkins:
        return [
            "Log a few check-ins (weight, meal adherence, training adherence, energy) "
            "so fueldesk can suggest gentle next-week tweaks."
        ]

    # Sort oldest → newest when dates available
    def _key(c: dict[str, Any]) -> str:
        return str(c.get("date") or "")

    ordered = sorted(checkins, key=_key)
    suggestions: list[str] = []

    weights = [float(c["weight_kg"]) for c in ordered if c.get("weight_kg") is not None]
    meal_adh = [
        float(c["adherence_meals"])
        for c in ordered
        if c.get("adherence_meals") is not None
    ]
    train_adh = [
        float(c["adherence_training"])
        for c in ordered
        if c.get("adherence_training") is not None
    ]
    energy = [float(c["energy"]) for c in ordered if c.get("energy") is not None]

    # Weight trend (need ≥3 points spanning ~1–2 weeks ideally)
    if len(weights) >= 3:
        first = sum(weights[:2]) / 2
        last = sum(weights[-2:]) / 2
        delta = last - first
        if goal == "lose":
            if abs(delta) < 0.3:
                suggestions.append(
                    "Weight looks roughly flat while goal is fat loss. "
                    "If adherence is solid, try a small ~100–150 kcal deficit next week "
                    "or add one extra walk. Reassess after 7 days."
                )
            elif delta > 0.5:
                suggestions.append(
                    "Weight has drifted up vs recent baseline on a lose goal. "
                    "Double-check portion accuracy and weekend adherence before cutting more."
                )
            elif delta < -1.5:
                suggestions.append(
                    "Weight is dropping quickly. Consider easing the deficit slightly "
                    "and watching energy/recovery."
                )
        elif goal == "gain":
            if abs(delta) < 0.3:
                suggestions.append(
                    "Weight is flat on a gain goal. Add ~150–200 kcal (mostly carbs around training) "
                    "and keep progressive overload."
                )
            elif delta > 1.5:
                suggestions.append(
                    "Weight is rising quickly on a gain goal. Slow the surplus a bit to limit fat gain."
                )
        else:  # maintain
            if abs(delta) > 1.0:
                suggestions.append(
                    "Weight moved more than ~1 kg vs recent baseline on maintain. "
                    "Nudge calories toward the direction that recenters you."
                )

    # Adherence
    if meal_adh:
        avg_m = sum(meal_adh) / len(meal_adh)
        if avg_m < 60:
            suggestions.append(
                f"Meal adherence averaging ~{avg_m:.0f}%. Simplify meals (repeat breakfast/lunch) "
                "before changing calorie targets."
            )
        elif avg_m >= 85 and goal == "lose" and len(weights) >= 3:
            first = sum(weights[:2]) / 2
            last = sum(weights[-2:]) / 2
            if abs(last - first) < 0.3:
                suggestions.append(
                    "High meal adherence with flat weight — protocol consistency is good; "
                    "a modest calorie or NEAT tweak is reasonable."
                )

    if train_adh:
        avg_t = sum(train_adh) / len(train_adh)
        if avg_t < 50:
            suggestions.append(
                f"Training adherence ~{avg_t:.0f}%. Drop to fewer weekly sessions you can keep, "
                "then rebuild — missed sessions beat perfect plans."
            )
        elif avg_t >= 85 and goal in ("gain", "maintain"):
            suggestions.append(
                "Training adherence is strong. Consider adding a set on main lifts "
                "or a small load increase next week."
            )

    if energy:
        avg_e = sum(energy) / len(energy)
        if avg_e <= 2.2:
            suggestions.append(
                "Energy scores are low. Prioritize sleep, keep protein high, and avoid stacking "
                "extra deficit + high volume the same week."
            )
        elif avg_e >= 4.2 and goal == "lose":
            suggestions.append(
                "Energy is solid — good sign your current deficit is sustainable for another week."
            )

    if current_calories:
        suggestions.append(
            f"Current daily target is {current_calories} kcal. Change targets only in small steps "
            f"(~100–200 kcal) and give each change ~7–14 days."
        )

    if not suggestions:
        suggestions.append(
            "Not enough signal for a strong tweak. Keep logging; stay consistent another week."
        )

    # Cap list length for UI
    return suggestions[:6]
