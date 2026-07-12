"""Weekly training protocol generator from profile constraints."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Each exercise: name, equipment tags (any match allows), min experience
# equipment tags: bodyweight, dumbbells, barbell, machines, bands, kettlebell, pullup_bar
EXERCISE_LIBRARY: list[dict[str, Any]] = [
    # Bodyweight
    {"name": "Push-ups", "focus": "push", "equipment": ["bodyweight"], "exp": "beginner", "sets": 3, "reps": "8-15"},
    {"name": "Bodyweight Squats", "focus": "legs", "equipment": ["bodyweight"], "exp": "beginner", "sets": 3, "reps": "10-20"},
    {"name": "Walking Lunges", "focus": "legs", "equipment": ["bodyweight"], "exp": "beginner", "sets": 3, "reps": "10/leg"},
    {"name": "Glute Bridges", "focus": "legs", "equipment": ["bodyweight"], "exp": "beginner", "sets": 3, "reps": "12-15"},
    {"name": "Plank", "focus": "core", "equipment": ["bodyweight"], "exp": "beginner", "sets": 3, "reps": "30-60s"},
    {"name": "Dead Bug", "focus": "core", "equipment": ["bodyweight"], "exp": "beginner", "sets": 3, "reps": "8/side"},
    {"name": "Bird Dog", "focus": "core", "equipment": ["bodyweight"], "exp": "beginner", "sets": 3, "reps": "8/side"},
    {"name": "Mountain Climbers", "focus": "conditioning", "equipment": ["bodyweight"], "exp": "beginner", "sets": 3, "reps": "20-30"},
    {"name": "Jumping Jacks", "focus": "conditioning", "equipment": ["bodyweight"], "exp": "beginner", "sets": 3, "reps": "30-45s"},
    {"name": "Inverted Rows (table)", "focus": "pull", "equipment": ["bodyweight"], "exp": "beginner", "sets": 3, "reps": "6-12"},
    {"name": "Pike Push-ups", "focus": "push", "equipment": ["bodyweight"], "exp": "intermediate", "sets": 3, "reps": "6-12"},
    {"name": "Bulgarian Split Squats", "focus": "legs", "equipment": ["bodyweight"], "exp": "intermediate", "sets": 3, "reps": "8/leg"},
    {"name": "Diamond Push-ups", "focus": "push", "equipment": ["bodyweight"], "exp": "intermediate", "sets": 3, "reps": "6-12"},
    # Dumbbells
    {"name": "Goblet Squat", "focus": "legs", "equipment": ["dumbbells"], "exp": "beginner", "sets": 3, "reps": "8-12"},
    {"name": "Dumbbell Romanian Deadlift", "focus": "legs", "equipment": ["dumbbells"], "exp": "beginner", "sets": 3, "reps": "8-12"},
    {"name": "Dumbbell Bench Press", "focus": "push", "equipment": ["dumbbells"], "exp": "beginner", "sets": 3, "reps": "8-12"},
    {"name": "Dumbbell Row", "focus": "pull", "equipment": ["dumbbells"], "exp": "beginner", "sets": 3, "reps": "8-12"},
    {"name": "Dumbbell Shoulder Press", "focus": "push", "equipment": ["dumbbells"], "exp": "beginner", "sets": 3, "reps": "8-12"},
    {"name": "Dumbbell Curl", "focus": "pull", "equipment": ["dumbbells"], "exp": "beginner", "sets": 2, "reps": "10-15"},
    {"name": "Dumbbell Lateral Raise", "focus": "push", "equipment": ["dumbbells"], "exp": "beginner", "sets": 2, "reps": "12-15"},
    {"name": "Dumbbell Lunges", "focus": "legs", "equipment": ["dumbbells"], "exp": "beginner", "sets": 3, "reps": "8/leg"},
    {"name": "Dumbbell Hip Thrust", "focus": "legs", "equipment": ["dumbbells"], "exp": "intermediate", "sets": 3, "reps": "8-12"},
    # Barbell
    {"name": "Back Squat", "focus": "legs", "equipment": ["barbell"], "exp": "intermediate", "sets": 4, "reps": "5-8"},
    {"name": "Conventional Deadlift", "focus": "legs", "equipment": ["barbell"], "exp": "intermediate", "sets": 3, "reps": "3-6"},
    {"name": "Barbell Bench Press", "focus": "push", "equipment": ["barbell"], "exp": "intermediate", "sets": 4, "reps": "5-8"},
    {"name": "Barbell Row", "focus": "pull", "equipment": ["barbell"], "exp": "intermediate", "sets": 3, "reps": "6-10"},
    {"name": "Overhead Press", "focus": "push", "equipment": ["barbell"], "exp": "intermediate", "sets": 3, "reps": "5-8"},
    {"name": "Romanian Deadlift", "focus": "legs", "equipment": ["barbell"], "exp": "intermediate", "sets": 3, "reps": "6-10"},
    # Machines
    {"name": "Leg Press", "focus": "legs", "equipment": ["machines"], "exp": "beginner", "sets": 3, "reps": "10-15"},
    {"name": "Lat Pulldown", "focus": "pull", "equipment": ["machines"], "exp": "beginner", "sets": 3, "reps": "8-12"},
    {"name": "Seated Cable Row", "focus": "pull", "equipment": ["machines"], "exp": "beginner", "sets": 3, "reps": "8-12"},
    {"name": "Chest Press Machine", "focus": "push", "equipment": ["machines"], "exp": "beginner", "sets": 3, "reps": "8-12"},
    {"name": "Leg Curl Machine", "focus": "legs", "equipment": ["machines"], "exp": "beginner", "sets": 3, "reps": "10-15"},
    {"name": "Cable Face Pull", "focus": "pull", "equipment": ["machines"], "exp": "beginner", "sets": 2, "reps": "12-15"},
    # Bands / kettlebell / pullup
    {"name": "Band Pull-aparts", "focus": "pull", "equipment": ["bands"], "exp": "beginner", "sets": 3, "reps": "15-20"},
    {"name": "Band Squats", "focus": "legs", "equipment": ["bands"], "exp": "beginner", "sets": 3, "reps": "12-15"},
    {"name": "Kettlebell Swing", "focus": "conditioning", "equipment": ["kettlebell"], "exp": "intermediate", "sets": 3, "reps": "12-15"},
    {"name": "Kettlebell Goblet Squat", "focus": "legs", "equipment": ["kettlebell"], "exp": "beginner", "sets": 3, "reps": "8-12"},
    {"name": "Pull-ups / Assisted Pull-ups", "focus": "pull", "equipment": ["pullup_bar"], "exp": "intermediate", "sets": 3, "reps": "4-10"},
    {"name": "Chin-ups", "focus": "pull", "equipment": ["pullup_bar"], "exp": "intermediate", "sets": 3, "reps": "4-10"},
    # Universal warm-up / finisher always available
    {"name": "Brisk Walk / Easy Bike", "focus": "conditioning", "equipment": ["bodyweight", "dumbbells", "barbell", "machines", "bands", "kettlebell", "pullup_bar"], "exp": "beginner", "sets": 1, "reps": "10-20 min"},
]

# Split templates by days_per_week (focus labels per training day index)
SPLITS: dict[int, list[str]] = {
    1: ["Full Body"],
    2: ["Full Body A", "Full Body B"],
    3: ["Push + Core", "Pull + Core", "Legs + Conditioning"],
    4: ["Upper Push", "Lower", "Upper Pull", "Full Body Light"],
    5: ["Push", "Pull", "Legs", "Upper", "Conditioning + Core"],
    6: ["Push", "Pull", "Legs", "Push", "Pull", "Legs Light"],
    7: ["Push", "Pull", "Legs", "Upper", "Lower", "Conditioning", "Mobility + Core"],
}

FOCUS_MAP: dict[str, list[str]] = {
    "Full Body": ["legs", "push", "pull", "core"],
    "Full Body A": ["legs", "push", "core"],
    "Full Body B": ["pull", "legs", "conditioning"],
    "Full Body Light": ["legs", "pull", "core"],
    "Push + Core": ["push", "core"],
    "Pull + Core": ["pull", "core"],
    "Legs + Conditioning": ["legs", "conditioning"],
    "Upper Push": ["push"],
    "Upper Pull": ["pull"],
    "Upper": ["push", "pull"],
    "Lower": ["legs", "core"],
    "Legs": ["legs"],
    "Legs Light": ["legs", "core"],
    "Push": ["push"],
    "Pull": ["pull"],
    "Conditioning + Core": ["conditioning", "core"],
    "Conditioning": ["conditioning"],
    "Mobility + Core": ["core", "conditioning"],
}


@dataclass(frozen=True)
class Exercise:
    name: str
    sets: int
    reps: str
    notes: str


def _normalize_equipment(equipment: list[str] | None) -> set[str]:
    if not equipment:
        return {"bodyweight"}
    eq = {e.strip().lower().replace(" ", "_") for e in equipment if e}
    # Always allow bodyweight movements as baseline
    eq.add("bodyweight")
    return eq


def _experience_ok(ex_exp: str, user_exp: str) -> bool:
    if user_exp == "intermediate":
        return True
    # beginner: only beginner exercises
    return ex_exp == "beginner"


def _allowed_exercises(equipment: set[str], experience: str) -> list[dict[str, Any]]:
    out = []
    for ex in EXERCISE_LIBRARY:
        tags = set(ex["equipment"])
        if tags & equipment and _experience_ok(ex["exp"], experience):
            out.append(ex)
    return out


def _stable_seed(*parts: Any) -> int:
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(h[:8], 16)


def _pick_for_focus(
    pool: list[dict[str, Any]],
    focuses: list[str],
    seed: int,
    count: int = 4,
) -> list[Exercise]:
    """Pick exercises covering requested focuses, deterministic by seed."""
    selected: list[Exercise] = []
    used_names: set[str] = set()

    # Round-robin through focuses
    by_focus: dict[str, list[dict[str, Any]]] = {}
    for ex in pool:
        by_focus.setdefault(ex["focus"], []).append(ex)

    i = 0
    while len(selected) < count and i < count * 4:
        focus = focuses[i % len(focuses)]
        candidates = [e for e in by_focus.get(focus, []) if e["name"] not in used_names]
        if not candidates:
            # fallback any unused
            candidates = [e for e in pool if e["name"] not in used_names]
        if not candidates:
            break
        idx = (seed + i * 7) % len(candidates)
        pick = candidates[idx]
        used_names.add(pick["name"])
        notes = "Stop if form breaks; consult a professional for injuries."
        if pick["exp"] == "intermediate":
            notes = "Prioritize form. Warm up sets first. " + notes
        selected.append(
            Exercise(
                name=pick["name"],
                sets=int(pick["sets"]),
                reps=str(pick["reps"]),
                notes=notes,
            )
        )
        i += 1

    return selected


def generate_workout_week(
    *,
    days_per_week: int,
    equipment: list[str] | None,
    experience: str = "beginner",
    goal: str = "maintain",
    seed_key: str = "",
) -> list[dict[str, Any]]:
    """
    Build a 7-day plan with `days_per_week` training days and rest days.

    Returns list of day dicts: {day, focus, exercises[{name,sets,reps,notes}]}
    """
    days_per_week = max(1, min(7, int(days_per_week)))
    experience = experience if experience in ("beginner", "intermediate") else "beginner"
    eq = _normalize_equipment(equipment)
    pool = _allowed_exercises(eq, experience)
    if not pool:
        # absolute fallback
        pool = [e for e in EXERCISE_LIBRARY if "bodyweight" in e["equipment"]]

    split = SPLITS.get(days_per_week, SPLITS[3])
    seed = _stable_seed(seed_key, days_per_week, sorted(eq), experience, goal)

    # Place training days evenly across the week
    if days_per_week == 7:
        train_indices = list(range(7))
    else:
        step = 7 / days_per_week
        train_indices = [int(i * step) % 7 for i in range(days_per_week)]
        # unique sorted
        train_indices = sorted(set(train_indices))
        # fill if collision reduced count
        j = 0
        while len(train_indices) < days_per_week:
            if j not in train_indices:
                train_indices.append(j)
            j += 1
            if j > 6:
                break
        train_indices = sorted(train_indices)[:days_per_week]

    days: list[dict[str, Any]] = []
    train_slot = 0
    for di, day_name in enumerate(DAY_NAMES):
        if di in train_indices and train_slot < len(split):
            focus_label = split[train_slot]
            focuses = FOCUS_MAP.get(focus_label, ["legs", "push", "pull"])
            # Slightly more volume for gain / intermediate
            count = 5 if experience == "intermediate" or goal == "gain" else 4
            if "conditioning" in focus_label.lower() or "mobility" in focus_label.lower():
                count = 3
            exercises = _pick_for_focus(pool, focuses, seed + train_slot * 13, count=count)
            days.append(
                {
                    "day": day_name,
                    "focus": focus_label,
                    "is_rest": False,
                    "exercises": [
                        {
                            "name": e.name,
                            "sets": e.sets,
                            "reps": e.reps,
                            "notes": e.notes,
                        }
                        for e in exercises
                    ],
                }
            )
            train_slot += 1
        else:
            days.append(
                {
                    "day": day_name,
                    "focus": "Rest / Walk",
                    "is_rest": True,
                    "exercises": [
                        {
                            "name": "Easy walk or mobility",
                            "sets": 1,
                            "reps": "20-40 min",
                            "notes": "Optional light movement. Sleep and protein still matter.",
                        }
                    ],
                }
            )

    return days


def count_training_days(days: list[dict[str, Any]]) -> int:
    return sum(1 for d in days if not d.get("is_rest", False))
