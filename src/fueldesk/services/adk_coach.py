"""Google ADK coach agent + offline multi-turn fallback.

Optional dependency: ``pip install -e ".[adk]"`` (google-adk[extensions]).
When ADK is missing or models fail, coach_chat falls back to offline heuristics.
Mutations are staged only — apply endpoints confirm before writing.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from sqlalchemy.orm import Session

from fueldesk.providers.offline import (
    estimate_equipment_offline,
    estimate_meal_offline,
    parse_profile_text,
)
from fueldesk.services import ai_assist, protocol as svc

# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

ADK_AVAILABLE = False
_ADK_IMPORT_ERROR: str | None = None

try:
    from google.adk.agents import LlmAgent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.adk.tools import FunctionTool
    from google.genai import types as genai_types

    ADK_AVAILABLE = True
except Exception as exc:  # noqa: BLE001 — optional dep
    _ADK_IMPORT_ERROR = str(exc)
    LlmAgent = None  # type: ignore[misc, assignment]
    Runner = None  # type: ignore[misc, assignment]
    InMemorySessionService = None  # type: ignore[misc, assignment]
    FunctionTool = None  # type: ignore[misc, assignment]
    genai_types = None  # type: ignore[misc, assignment]


APP_NAME = "fueldesk"
COACH_USER_ID = "local-user"

DISCLAIMER = (
    "Educational coaching only — not medical advice. Estimates are approximate; "
    "review before applying."
)

INSTALL_HINT = (
    'Install ADK coach: pip install -e ".[adk]" then set GOOGLE_API_KEY or '
    "GEMINI_API_KEY (or choose Gemini under Settings)."
)

SUGGESTED_PROMPTS = [
    "Build my plan from my profile",
    "I'm vegetarian with dumbbells — update equipment",
    "Explain my calories and macros",
    "Parse: 28F, 165cm, 62kg, lose fat, 4 days/week",
    "Estimate meal: grilled chicken rice salad",
    "What equipment do I have set?",
]


@dataclass
class CoachTurnResult:
    reply: str
    tools_used: list[str] = field(default_factory=list)
    staged: dict[str, Any] | None = None
    confidence: float | None = None
    provider: str = "offline"
    adk_available: bool = False
    fallback_used: bool = False
    messages: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# In-process staged mutations + chat transcripts (local single-user)
_STAGED: dict[str, dict[str, Any]] = {}
_CHAT_HISTORY: dict[str, list[dict[str, Any]]] = {}
_ADK_SESSION_IDS: dict[str, str] = {}
_ADK_SESSION_SERVICE: Any = None


def adk_status() -> dict[str, Any]:
    return {
        "available": ADK_AVAILABLE,
        "import_error": _ADK_IMPORT_ERROR,
        "install_hint": INSTALL_HINT if not ADK_AVAILABLE else "",
    }


def get_chat_history(session_key: str = "default") -> list[dict[str, Any]]:
    return list(_CHAT_HISTORY.get(session_key, []))


def clear_chat_history(session_key: str = "default") -> None:
    _CHAT_HISTORY.pop(session_key, None)
    _ADK_SESSION_IDS.pop(session_key, None)
    _STAGED.pop(session_key, None)


def get_staged(session_key: str = "default") -> dict[str, Any] | None:
    return _STAGED.get(session_key)


def pop_staged(session_key: str = "default") -> dict[str, Any] | None:
    return _STAGED.pop(session_key, None)


def set_staged(session_key: str, payload: dict[str, Any]) -> None:
    _STAGED[session_key] = payload


# ---------------------------------------------------------------------------
# Domain tools (confirm-before-apply for mutations)
# ---------------------------------------------------------------------------


def tool_get_profile_summary(session: Session) -> dict[str, Any]:
    profile = svc.get_profile(session)
    if profile is None:
        return {
            "ok": False,
            "message": "No profile yet. Ask the user to describe themselves or open Profile.",
        }
    return {
        "ok": True,
        "profile": {
            "sex": profile.sex,
            "age": profile.age,
            "height_cm": profile.height_cm,
            "weight_kg": profile.weight_kg,
            "activity_level": profile.activity_level,
            "goal": profile.goal,
            "diet_flags": list(profile.diet_flags or []),
            "equipment": list(profile.equipment or []),
            "days_per_week": profile.days_per_week,
            "experience": profile.experience,
            "notes": (profile.notes or "")[:300],
        },
    }


def tool_get_targets_explanation(session: Session) -> dict[str, Any]:
    targets = svc.get_latest_targets(session)
    profile = svc.get_profile(session)
    if targets is None:
        return {
            "ok": False,
            "message": "No targets yet. Complete a profile and generate a protocol first.",
        }
    return {
        "ok": True,
        "targets": {
            "bmr": targets.bmr,
            "tdee": targets.tdee,
            "calorie_target": targets.calorie_target,
            "protein_g": targets.protein_g,
            "carbs_g": targets.carbs_g,
            "fat_g": targets.fat_g,
            "formula_notes": targets.formula_notes,
            "goal": profile.goal if profile else None,
        },
        "disclaimer": DISCLAIMER,
    }


def tool_parse_profile_text(session: Session, text: str) -> dict[str, Any]:
    result = ai_assist.parse_profile(session, text)
    return {
        "ok": True,
        "fields": result.fields,
        "confidence": result.confidence,
        "notes": result.notes,
        "provider": result.provider,
        "fallback_used": result.fallback_used,
        "staged_kind": "profile",
        "message": "Parsed fields ready — user must confirm before apply.",
    }


def tool_estimate_meal_from_caption(session: Session, caption: str) -> dict[str, Any]:
    result = ai_assist.estimate_meal(session, caption=caption)
    d = result.as_dict()
    d["ok"] = True
    d["staged_kind"] = "meal"
    d["message"] = "Meal estimate ready — confirm before saving to check-in notes."
    return d


def tool_estimate_equipment_from_caption(session: Session, caption: str) -> dict[str, Any]:
    result = ai_assist.estimate_equipment(session, caption=caption)
    d = result.as_dict()
    d["ok"] = True
    d["staged_kind"] = "equipment"
    d["message"] = "Equipment suggestion ready — confirm before applying to profile."
    return d


def tool_stage_profile_update(
    session: Session, fields_json: str, session_key: str = "default"
) -> dict[str, Any]:
    """Stage profile fields for confirm-before-apply (does not write DB)."""
    try:
        fields = json.loads(fields_json) if isinstance(fields_json, str) else fields_json
    except json.JSONDecodeError:
        return {"ok": False, "message": "fields_json must be valid JSON object."}
    if not isinstance(fields, dict):
        return {"ok": False, "message": "fields must be an object."}
    normalized = ai_assist.normalize_profile_fields(fields)
    payload = {
        "kind": "profile",
        "fields": normalized,
        "confidence": float(fields.get("confidence") or 0.6),
        "source": "adk_coach",
    }
    set_staged(session_key, payload)
    return {
        "ok": True,
        "staged": True,
        "kind": "profile",
        "fields": normalized,
        "message": "Profile update staged. User must click Apply in the UI.",
    }


def tool_stage_regenerate_protocol(
    session: Session, session_key: str = "default"
) -> dict[str, Any]:
    profile = svc.get_profile(session)
    if profile is None:
        return {
            "ok": False,
            "message": "No profile — cannot regenerate. Create/apply a profile first.",
        }
    payload = {
        "kind": "regenerate_protocol",
        "source": "adk_coach",
        "profile_id": profile.id,
    }
    set_staged(session_key, payload)
    return {
        "ok": True,
        "staged": True,
        "kind": "regenerate_protocol",
        "message": "Protocol regeneration staged. User must confirm Apply in the UI.",
    }


def apply_staged(session: Session, session_key: str = "default") -> dict[str, Any]:
    """Apply previously staged mutation (confirm endpoint)."""
    staged = pop_staged(session_key)
    if not staged:
        return {"ok": False, "message": "Nothing staged to apply."}
    kind = staged.get("kind")
    if kind == "profile":
        profile = ai_assist.apply_profile_and_generate(session, staged["fields"])
        return {
            "ok": True,
            "kind": "profile",
            "message": "Profile applied and protocol regenerated.",
            "profile_id": profile.id,
        }
    if kind == "equipment":
        eq = staged.get("equipment") or ["bodyweight"]
        profile = ai_assist.apply_equipment(session, list(eq), regenerate=True)
        return {
            "ok": True,
            "kind": "equipment",
            "message": "Equipment applied and protocol regenerated.",
            "equipment": list(profile.equipment or []),
        }
    if kind == "regenerate_protocol":
        profile = svc.get_profile(session)
        if profile is None:
            return {"ok": False, "message": "No profile."}
        svc.generate_protocol(session, profile)
        return {
            "ok": True,
            "kind": "regenerate_protocol",
            "message": "Weekly protocol regenerated from current profile.",
        }
    if kind == "meal":
        note = ai_assist.meal_estimate_to_note(staged.get("estimate") or {})
        ai_assist.append_meal_note_to_checkin(session, note)
        return {
            "ok": True,
            "kind": "meal",
            "message": "Meal estimate saved to today's check-in notes.",
        }
    return {"ok": False, "message": f"Unknown staged kind: {kind}"}


# ---------------------------------------------------------------------------
# Offline coach (always available)
# ---------------------------------------------------------------------------


def _unique(seq: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _offline_coach_reply(
    session: Session,
    user_text: str,
    session_key: str = "default",
) -> CoachTurnResult:
    text = (user_text or "").strip()
    low = text.lower()
    tools: list[str] = []
    staged: dict[str, Any] | None = None
    conf: float | None = None
    parts: list[str] = []

    if not text:
        return CoachTurnResult(
            reply="Tell me about your goals, body stats, meals, or equipment — I'll help.",
            provider="offline",
            adk_available=ADK_AVAILABLE,
        )

    meal_only = bool(re.search(r"\b(estimate meal|meal:|plate|food photo)\b", low))
    equip_only = bool(re.search(r"\b(estimate equipment|equipment:|gym photo)\b", low))

    # Explain targets
    if any(
        k in low for k in ("explain", "calories", "macros", "tdee", "bmr", "target", "protein")
    ) and not meal_only:
        tools.append("get_targets_explanation")
        data = tool_get_targets_explanation(session)
        if not data.get("ok"):
            parts.append(data.get("message") or "No targets yet.")
            tools.append("get_profile_summary")
            prof = tool_get_profile_summary(session)
            if not prof.get("ok"):
                parts.append("Next: complete your profile (or paste a description).")
        else:
            t = data["targets"]
            parts.append(
                "Your targets (goal: {goal}): **{cal} kcal**, protein **{p}g**, "
                "carbs **{c}g**, fat **{f}g**.\n"
                "BMR {bmr} → TDEE {tdee} (Mifflin-St Jeor + activity).\n"
                "{disc}".format(
                    goal=t.get("goal"),
                    cal=t["calorie_target"],
                    p=t["protein_g"],
                    c=t["carbs_g"],
                    f=t["fat_g"],
                    bmr=t["bmr"],
                    tdee=t["tdee"],
                    disc=DISCLAIMER,
                )
            )
            conf = 0.85

    # Profile summary
    if any(k in low for k in ("my profile", "who am i", "current profile", "what equipment")):
        tools.append("get_profile_summary")
        data = tool_get_profile_summary(session)
        if data.get("ok"):
            p = data["profile"]
            parts.append(
                "Profile: {sex}, {age}y, {h}cm, {w}kg · goal **{goal}** · "
                "{days} days/week · equipment: {eq} · diet: {diet}.".format(
                    sex=p["sex"],
                    age=p["age"],
                    h=p["height_cm"],
                    w=p["weight_kg"],
                    goal=p["goal"],
                    days=p["days_per_week"],
                    eq=", ".join(p["equipment"]) or "none",
                    diet=", ".join(p["diet_flags"]) or "none",
                )
            )
            conf = 0.9
        else:
            parts.append(data.get("message") or "No profile.")

    parse_trigger = any(
        k in low
        for k in (
            "parse",
            "i'm ",
            "i am ",
            "describe",
            "years old",
            "cm",
            "kg",
            "vegetarian",
            "vegan",
            "dumbbell",
            "build my plan",
            "update profile",
            "set up",
        )
    )

    if parse_trigger and not (meal_only or (equip_only and "parse" not in low)):
        parse_text = text
        m = re.search(r"(?:parse|describe|update)[:\s]+(.+)", text, re.I | re.S)
        if m:
            parse_text = m.group(1).strip()
        tools.append("parse_profile_text")
        parsed = tool_parse_profile_text(session, parse_text)
        fields = parsed.get("fields") or {}
        conf = float(parsed.get("confidence") or 0)
        tools.append("stage_profile_update")
        staged_payload = {
            "kind": "profile",
            "fields": ai_assist.normalize_profile_fields(fields),
            "confidence": conf,
            "source": "offline_coach",
            "notes": parsed.get("notes") or [],
        }
        set_staged(session_key, staged_payload)
        staged = staged_payload
        f = staged_payload["fields"]
        parts.append(
            "I parsed a profile (confidence **{conf:.0%}**, provider {prov}):\n"
            "- {sex}, age {age}, {h} cm, {w} kg\n"
            "- Goal: {goal} · Activity: {act} · {days} days/week · {exp}\n"
            "- Diet: {diet}\n"
            "- Equipment: {eq}\n"
            "Review the staged update below, then **Apply** to save & regenerate protocol.".format(
                conf=conf,
                prov=parsed.get("provider"),
                sex=f.get("sex"),
                age=f.get("age"),
                h=f.get("height_cm"),
                w=f.get("weight_kg"),
                goal=f.get("goal"),
                act=f.get("activity_level"),
                days=f.get("days_per_week"),
                exp=f.get("experience"),
                diet=", ".join(f.get("diet_flags") or []) or "none",
                eq=", ".join(f.get("equipment") or []),
            )
        )
        if parsed.get("notes"):
            parts.append("Notes: " + "; ".join(list(parsed["notes"])[:4]))

    # Meal estimate
    if meal_only or re.search(r"\b(estimate meal|meal:|i ate|for lunch|for dinner)\b", low):
        cap = text
        m = re.search(r"(?:meal|ate|lunch|dinner|estimate meal)[:\s]+(.+)", text, re.I | re.S)
        if m:
            cap = m.group(1).strip()
        tools.append("estimate_meal_from_caption")
        est = tool_estimate_meal_from_caption(session, cap)
        conf = float(est.get("confidence") or 0)
        items = est.get("items") or []
        lines = [
            "- {name}: {cal} kcal (P{p} C{c} F{f})".format(
                name=it.get("name"),
                cal=it.get("calories"),
                p=it.get("protein_g"),
                c=it.get("carbs_g"),
                f=it.get("fat_g"),
            )
            for it in items
        ]
        staged_payload = {
            "kind": "meal",
            "estimate": est,
            "confidence": conf,
            "source": "offline_coach",
        }
        set_staged(session_key, staged_payload)
        staged = staged_payload
        parts.append(
            "Meal estimate (~{tot} kcal, confidence **{conf:.0%}**):\n{lines}\n"
            "{disc}\nConfirm **Apply** to save to today's check-in notes.".format(
                tot=est.get("total_calories"),
                conf=conf,
                lines="\n".join(lines),
                disc=est.get("disclaimer") or DISCLAIMER,
            )
        )

    # Equipment estimate
    if equip_only or (
        re.search(r"\b(equipment|dumbbells|barbell|kettlebell|pull-?up)\b", low)
        and any(k in low for k in ("estimate", "update", "set", "i have", "photo", "caption"))
        and "stage_profile_update" not in tools
    ):
        cap = text
        m = re.search(r"(?:equipment|have|update)[:\s]+(.+)", text, re.I | re.S)
        if m:
            cap = m.group(1).strip()
        tools.append("estimate_equipment_from_caption")
        est = tool_estimate_equipment_from_caption(session, cap)
        conf = float(est.get("confidence") or 0)
        eq = est.get("equipment") or []
        if eq:
            staged_payload = {
                "kind": "equipment",
                "equipment": eq,
                "confidence": conf,
                "source": "offline_coach",
                "notes": est.get("notes") or [],
            }
            set_staged(session_key, staged_payload)
            staged = staged_payload
            parts.append(
                "Suggested equipment (confidence **{conf:.0%}**): **{eq}**.\n"
                "Confirm **Apply** to update profile & regenerate training.".format(
                    conf=conf, eq=", ".join(eq)
                )
            )
        else:
            parts.append(
                "Couldn't detect equipment offline. Try a caption like "
                "`rack, bench, dumbbells` or pick chips under AI → Equipment."
            )

    # Regenerate
    if any(
        k in low
        for k in ("regenerate", "rebuild", "new protocol", "build my plan", "generate plan")
    ):
        tools.append("stage_regenerate_protocol")
        reg = tool_stage_regenerate_protocol(session, session_key=session_key)
        if reg.get("ok"):
            if staged is None or staged.get("kind") != "profile":
                staged = get_staged(session_key)
            parts.append(
                "Protocol regeneration is staged. Confirm **Apply** to rebuild this week's "
                "meals + training from your current profile."
            )
        else:
            parts.append(reg.get("message") or "Cannot regenerate yet.")

    if not parts:
        tools.append("get_profile_summary")
        prof = tool_get_profile_summary(session)
        if prof.get("ok"):
            p = prof["profile"]
            parts.append(
                "I'm your fueldesk coach (offline mode). You already have a profile "
                "({goal}, {days} days/week). Try:\n"
                '- "Explain my calories"\n'
                '- "Parse: 30M 80kg 180cm gain dumbbells 4 days/week"\n'
                '- "Estimate meal: chicken rice salad"\n'
                '- "Regenerate protocol"'.format(goal=p["goal"], days=p["days_per_week"])
            )
        else:
            extra = INSTALL_HINT if not ADK_AVAILABLE else (
                "ADK is available for richer multi-turn coaching."
            )
            parts.append(
                "Welcome! I'm the fueldesk coach. Paste something like:\n"
                '"28F, 165cm, 62kg, vegetarian, lose fat, 4 days/week dumbbells"\n'
                "I'll stage a profile for you to confirm. " + extra
            )

    tools_u = _unique(tools)
    reply = "\n\n".join(parts)
    if not ADK_AVAILABLE:
        reply += "\n\n_Offline coach · " + INSTALL_HINT + "_"

    return CoachTurnResult(
        reply=reply,
        tools_used=tools_u,
        staged=staged or get_staged(session_key),
        confidence=conf,
        provider="offline",
        adk_available=ADK_AVAILABLE,
        fallback_used=False,
    )


# ---------------------------------------------------------------------------
# ADK agent
# ---------------------------------------------------------------------------


def _resolve_adk_model(cfg: Any) -> str:
    """Return ADK model string for Gemini or LiteLLM-backed providers."""
    provider = getattr(cfg, "provider", "offline") or "offline"
    model = (getattr(cfg, "model", None) or "").strip()

    if provider == "gemini":
        return model or "gemini-2.0-flash"
    if provider == "ollama":
        m = model or "llama3.2"
        if not m.startswith("ollama"):
            m = f"ollama_chat/{m}"
        return m
    if provider == "openai_compatible":
        m = model or "gpt-4o-mini"
        if "/" not in m and not m.startswith("openai"):
            m = f"openai/{m}"
        return m
    if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        return model or "gemini-2.0-flash"
    return model or "gemini-2.0-flash"


def _ensure_gemini_env(cfg: Any) -> None:
    key = (
        os.environ.get("GOOGLE_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or getattr(cfg, "api_key", "")
        or ""
    ).strip()
    if key and not os.environ.get("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = key
    if key and not os.environ.get("GEMINI_API_KEY"):
        os.environ["GEMINI_API_KEY"] = key


def _build_adk_tools(session: Session, session_key: str) -> list[Any]:
    """Build FunctionTools bound to the current DB session."""

    def get_profile_summary() -> dict[str, Any]:
        """Return the user's current fueldesk profile summary (read-only)."""
        return tool_get_profile_summary(session)

    def get_targets_explanation() -> dict[str, Any]:
        """Explain BMR, TDEE, calorie and macro targets with formula notes (read-only)."""
        return tool_get_targets_explanation(session)

    def parse_profile_text(text: str) -> dict[str, Any]:
        """Parse free-text body stats into structured profile fields. Does not save."""
        return tool_parse_profile_text(session, text)

    def estimate_meal_from_caption(caption: str) -> dict[str, Any]:
        """Estimate meal macros from a text caption. Estimates only — not medical analysis."""
        return tool_estimate_meal_from_caption(session, caption)

    def estimate_equipment_from_caption(caption: str) -> dict[str, Any]:
        """Detect gym equipment tags from a caption. Does not save until user confirms."""
        return tool_estimate_equipment_from_caption(session, caption)

    def stage_profile_update(fields_json: str) -> dict[str, Any]:
        """Stage profile field updates as JSON for user confirm-before-apply. Does not write DB."""
        return tool_stage_profile_update(session, fields_json, session_key=session_key)

    def stage_regenerate_protocol() -> dict[str, Any]:
        """Stage weekly meal+training protocol regeneration for user confirmation."""
        return tool_stage_regenerate_protocol(session, session_key=session_key)

    return [
        FunctionTool(get_profile_summary),
        FunctionTool(get_targets_explanation),
        FunctionTool(parse_profile_text),
        FunctionTool(estimate_meal_from_caption),
        FunctionTool(estimate_equipment_from_caption),
        FunctionTool(stage_profile_update),
        FunctionTool(stage_regenerate_protocol),
    ]


def _make_runner(session: Session, session_key: str, cfg: Any) -> Any:
    global _ADK_SESSION_SERVICE
    if not ADK_AVAILABLE:
        raise RuntimeError("ADK not installed")

    _ensure_gemini_env(cfg)
    model = _resolve_adk_model(cfg)
    tools = _build_adk_tools(session, session_key)
    instruction = (
        "You are fueldesk Coach — a friendly, practical fitness & nutrition planning assistant "
        "for a local-first app. You help with profile setup, calorie/macro explanations, "
        "meal estimates, equipment detection, and weekly protocol regeneration.\n\n"
        "Rules:\n"
        "- Never claim medical authority. Label estimates as estimates.\n"
        "- Use tools for profile, targets, parse, meal/equipment estimates, and staging mutations.\n"
        "- Mutations must ONLY be staged via stage_profile_update or stage_regenerate_protocol; "
        "the user confirms Apply in the UI.\n"
        "- When parsing profiles, call parse_profile_text then stage_profile_update with the fields JSON.\n"
        "- Be concise, warm, and action-oriented. Prefer short bullet summaries.\n"
        "- If data is missing, ask for one clear next step.\n"
    )

    agent = LlmAgent(
        name="fueldesk_coach",
        model=model,
        description="Local fueldesk fitness protocol coach with confirm-before-apply tools.",
        instruction=instruction,
        tools=tools,
    )

    if _ADK_SESSION_SERVICE is None:
        _ADK_SESSION_SERVICE = InMemorySessionService()

    return Runner(
        agent=agent,
        app_name=APP_NAME,
        session_service=_ADK_SESSION_SERVICE,
    )


def _maybe_await(result: Any) -> Any:
    if asyncio.iscoroutine(result):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Best-effort: create a new loop in a thread is heavy; raise for fallback
                raise RuntimeError("async create_session while loop running")
            return loop.run_until_complete(result)
        except RuntimeError:
            return asyncio.run(result)
    return result


def _run_adk_turn(
    session: Session,
    user_text: str,
    *,
    session_key: str,
    cfg: Any,
) -> CoachTurnResult:
    runner = _make_runner(session, session_key, cfg)
    assert _ADK_SESSION_SERVICE is not None

    adk_sid = _ADK_SESSION_IDS.get(session_key)
    if not adk_sid:
        adk_sid = f"fueldesk-{session_key}-{uuid.uuid4().hex[:10]}"
        create_sync = getattr(_ADK_SESSION_SERVICE, "create_session_sync", None)
        create = getattr(_ADK_SESSION_SERVICE, "create_session", None)
        if create_sync:
            create_sync(app_name=APP_NAME, user_id=COACH_USER_ID, session_id=adk_sid)
        elif create:
            _maybe_await(
                create(app_name=APP_NAME, user_id=COACH_USER_ID, session_id=adk_sid)
            )
        _ADK_SESSION_IDS[session_key] = adk_sid

    content = genai_types.Content(
        role="user",
        parts=[genai_types.Part(text=user_text)],
    )

    tools_used: list[str] = []
    final_text_parts: list[str] = []

    def _consume_event(event: Any) -> None:
        fn_calls = None
        if hasattr(event, "get_function_calls"):
            try:
                fn_calls = event.get_function_calls()
            except Exception:  # noqa: BLE001
                fn_calls = None
        if fn_calls:
            for fc in fn_calls:
                name = getattr(fc, "name", None) or str(fc)
                if name and name not in tools_used:
                    tools_used.append(name)

        is_final = False
        if hasattr(event, "is_final_response"):
            try:
                is_final = bool(event.is_final_response())
            except Exception:  # noqa: BLE001
                is_final = False

        parts = []
        if getattr(event, "content", None) and getattr(event.content, "parts", None):
            for part in event.content.parts:
                t = getattr(part, "text", None)
                if t:
                    parts.append(t)
        if parts:
            if is_final:
                final_text_parts.clear()
            final_text_parts.extend(parts)

    if hasattr(runner, "run"):
        events = runner.run(
            user_id=COACH_USER_ID,
            session_id=adk_sid,
            new_message=content,
        )
        for event in events:
            _consume_event(event)
    elif hasattr(runner, "run_async"):

        async def _async_run() -> None:
            async for event in runner.run_async(
                user_id=COACH_USER_ID,
                session_id=adk_sid,
                new_message=content,
            ):
                _consume_event(event)

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                raise RuntimeError("async loop already running")
            loop.run_until_complete(_async_run())
        except RuntimeError:
            asyncio.run(_async_run())
    else:
        raise RuntimeError("ADK Runner has no run/run_async")

    reply = "\n".join(p for p in final_text_parts if p).strip()
    if not reply:
        reply = (
            "I ran your request with the ADK coach tools. "
            "Check any staged actions below to confirm."
        )

    staged = get_staged(session_key)
    return CoachTurnResult(
        reply=reply,
        tools_used=tools_used,
        staged=staged,
        confidence=0.75 if tools_used else 0.5,
        provider="adk",
        adk_available=True,
        fallback_used=False,
    )


def _should_use_adk(cfg: Any) -> bool:
    if not ADK_AVAILABLE:
        return False
    provider = getattr(cfg, "provider", "offline") or "offline"
    if provider == "gemini":
        return True
    if provider in ("ollama", "openai_compatible"):
        return True
    if provider == "offline":
        if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"):
            return True
        if getattr(cfg, "api_key", None) and getattr(cfg, "model", None):
            # key stored for gemini-ish use without provider switch
            return False
    return False


def coach_chat(
    session: Session,
    user_text: str,
    *,
    session_key: str = "default",
    history: list[dict[str, Any]] | None = None,
) -> CoachTurnResult:
    """Multi-turn coach entrypoint. ADK when available + configured; else offline."""
    cfg = ai_assist.resolve_ai_config(session)
    hist = history if history is not None else get_chat_history(session_key)

    user_msg = {
        "role": "user",
        "content": user_text,
        "tools_used": [],
        "provider": "user",
    }
    hist.append(user_msg)

    if _should_use_adk(cfg):
        try:
            result = _run_adk_turn(session, user_text, session_key=session_key, cfg=cfg)
        except Exception as exc:  # noqa: BLE001
            offline = _offline_coach_reply(session, user_text, session_key=session_key)
            offline.fallback_used = True
            offline.reply = f"(ADK unavailable: {exc})\n\n" + offline.reply
            offline.adk_available = ADK_AVAILABLE
            result = offline
    else:
        result = _offline_coach_reply(session, user_text, session_key=session_key)
        result.adk_available = ADK_AVAILABLE

    assistant_msg = {
        "role": "assistant",
        "content": result.reply,
        "tools_used": result.tools_used,
        "provider": result.provider,
        "confidence": result.confidence,
        "staged": result.staged,
        "fallback_used": result.fallback_used,
    }
    hist.append(assistant_msg)
    _CHAT_HISTORY[session_key] = hist[-40:]
    result.messages = list(_CHAT_HISTORY[session_key])
    result.staged = result.staged or get_staged(session_key)
    return result


def offline_tools_bundle() -> dict[str, Callable[..., Any]]:
    return {
        "parse_profile_text": parse_profile_text,
        "estimate_meal_offline": estimate_meal_offline,
        "estimate_equipment_offline": estimate_equipment_offline,
        "tool_get_profile_summary": tool_get_profile_summary,
        "tool_get_targets_explanation": tool_get_targets_explanation,
        "tool_parse_profile_text": tool_parse_profile_text,
        "tool_estimate_meal_from_caption": tool_estimate_meal_from_caption,
        "tool_estimate_equipment_from_caption": tool_estimate_equipment_from_caption,
        "tool_stage_profile_update": tool_stage_profile_update,
        "tool_stage_regenerate_protocol": tool_stage_regenerate_protocol,
    }
