"""AI Assist + Settings routes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from fueldesk.db.session import get_engine, get_session_factory
from fueldesk.domain.targets import validate_profile_ranges
from fueldesk.services import ai_assist, protocol as svc
from fueldesk.web.routes import (
    ACTIVITY_OPTIONS,
    DIET_OPTIONS,
    EQUIPMENT_OPTIONS,
    GOAL_OPTIONS,
    _base_ctx,
    _db,
    _flash,
)

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

MAX_UPLOAD = ai_assist.MAX_UPLOAD_BYTES


def _conf_badge(conf: float) -> str:
    if conf >= 0.7:
        return "high"
    if conf >= 0.4:
        return "medium"
    return "low"


def _provider_ctx(session) -> dict[str, Any]:
    cfg = ai_assist.resolve_ai_config(session)
    public = cfg.as_public_dict()
    return {"ai_config": public, "provider_label": public["label"]}


@router.get("/ai", response_class=HTMLResponse)
def ai_hub(request: Request) -> HTMLResponse:
    session = _db()
    try:
        profile = svc.get_profile(session)
        return templates.TemplateResponse(
            request,
            "ai_hub.html",
            _base_ctx(request, page="ai", profile=profile, **_provider_ctx(session)),
        )
    finally:
        session.close()


@router.get("/ai/profile", response_class=HTMLResponse)
def ai_profile_get(request: Request) -> HTMLResponse:
    session = _db()
    try:
        profile = svc.get_profile(session)
        preview = request.session.pop("ai_profile_preview", None)
        return templates.TemplateResponse(
            request,
            "ai_profile.html",
            _base_ctx(
                request,
                page="ai",
                profile=profile,
                preview=preview,
                conf_level=_conf_badge(float((preview or {}).get("confidence") or 0)),
                diet_options=DIET_OPTIONS,
                equipment_options=EQUIPMENT_OPTIONS,
                activity_options=ACTIVITY_OPTIONS,
                goal_options=GOAL_OPTIONS,
                **_provider_ctx(session),
            ),
        )
    finally:
        session.close()


@router.post("/ai/profile", response_model=None)
async def ai_profile_post(request: Request):
    form = await request.form()
    action = str(form.get("action") or "parse")
    session = _db()
    try:
        if action == "parse":
            text = str(form.get("text") or "").strip()
            if not text:
                _flash(request, "Enter a short description of yourself.", "error")
                return RedirectResponse("/ai/profile", status_code=303)
            result = ai_assist.parse_profile(session, text)
            request.session["ai_profile_preview"] = result.as_dict()
            if result.fallback_used:
                _flash(
                    request,
                    "Remote provider unavailable — used offline heuristics.",
                    "info",
                )
            return RedirectResponse("/ai/profile", status_code=303)

        if action == "discard":
            request.session.pop("ai_profile_preview", None)
            _flash(request, "AI profile preview discarded.", "info")
            return RedirectResponse("/ai/profile", status_code=303)

        if action == "apply":
            # Build fields from editable form
            diet_flags = [v for v in form.getlist("diet_flags") if v]
            equipment = [v for v in form.getlist("equipment") if v] or ["bodyweight"]
            try:
                data = {
                    "sex": str(form.get("sex") or "male"),
                    "age": int(str(form.get("age") or "30")),
                    "height_cm": float(str(form.get("height_cm") or "170")),
                    "weight_kg": float(str(form.get("weight_kg") or "70")),
                    "activity_level": str(form.get("activity_level") or "moderate"),
                    "goal": str(form.get("goal") or "maintain"),
                    "diet_flags": diet_flags,
                    "equipment": equipment,
                    "days_per_week": int(str(form.get("days_per_week") or "3")),
                    "experience": str(form.get("experience") or "beginner"),
                    "notes": str(form.get("notes") or ""),
                    "units": "metric",
                }
            except ValueError:
                _flash(request, "Invalid numbers in preview fields.", "error")
                return RedirectResponse("/ai/profile", status_code=303)

            errors = validate_profile_ranges(
                age=data["age"], height_cm=data["height_cm"], weight_kg=data["weight_kg"]
            )
            if errors:
                _flash(request, "; ".join(errors), "error")
                return RedirectResponse("/ai/profile", status_code=303)

            try:
                ai_assist.apply_profile_and_generate(session, data)
                session.commit()
                request.session.pop("ai_profile_preview", None)
                _flash(request, "Profile applied and protocol regenerated.", "success")
                return RedirectResponse("/", status_code=303)
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                _flash(request, f"Apply failed: {exc}", "error")
                return RedirectResponse("/ai/profile", status_code=303)

        _flash(request, "Unknown action.", "error")
        return RedirectResponse("/ai/profile", status_code=303)
    finally:
        session.close()


@router.get("/ai/meal", response_class=HTMLResponse)
def ai_meal_get(request: Request) -> HTMLResponse:
    session = _db()
    try:
        profile = svc.get_profile(session)
        estimate = request.session.get("ai_meal_estimate")
        return templates.TemplateResponse(
            request,
            "ai_meal.html",
            _base_ctx(
                request,
                page="ai",
                profile=profile,
                estimate=estimate,
                conf_level=_conf_badge(float((estimate or {}).get("confidence") or 0)),
                **_provider_ctx(session),
            ),
        )
    finally:
        session.close()


async def _read_upload(upload: UploadFile | None) -> tuple[bytes | None, str, str | None]:
    if upload is None or not upload.filename:
        return None, "", None
    data = await upload.read()
    if len(data) > MAX_UPLOAD:
        return None, upload.filename, f"Image too large (max {MAX_UPLOAD // (1024*1024)} MB)."
    if data and not (
        upload.content_type or ""
    ).startswith("image/") and not upload.filename.lower().endswith(
        (".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic")
    ):
        return None, upload.filename, "Please upload an image file."
    return data, upload.filename, None


@router.post("/ai/meal", response_model=None)
async def ai_meal_post(
    request: Request,
    action: str = Form("estimate"),
    caption: str = Form(""),
    image: UploadFile | None = File(None),
):
    session = _db()
    try:
        if action == "discard":
            request.session.pop("ai_meal_estimate", None)
            _flash(request, "Meal estimate discarded.", "info")
            return RedirectResponse("/ai/meal", status_code=303)

        if action == "estimate":
            image_bytes, filename, err = await _read_upload(image)
            if err:
                _flash(request, err, "error")
                return RedirectResponse("/ai/meal", status_code=303)
            if not image_bytes and not caption.strip():
                _flash(request, "Upload a meal photo and/or add a caption.", "error")
                return RedirectResponse("/ai/meal", status_code=303)
            result = ai_assist.estimate_meal(
                session,
                image_bytes=image_bytes,
                filename=filename,
                caption=caption,
            )
            request.session["ai_meal_estimate"] = result.as_dict()
            if result.fallback_used:
                _flash(request, "Remote provider unavailable — offline estimate used.", "info")
            return RedirectResponse("/ai/meal", status_code=303)

        if action == "save_note":
            form = await request.form()
            # Rebuild estimate from edited fields
            names = form.getlist("item_name")
            cals = form.getlist("item_calories")
            prots = form.getlist("item_protein")
            carbs = form.getlist("item_carbs")
            fats = form.getlist("item_fat")
            items = []
            for i in range(len(names)):
                try:
                    items.append(
                        {
                            "name": str(names[i]),
                            "calories": int(float(str(cals[i] or 0))),
                            "protein_g": float(str(prots[i] or 0)),
                            "carbs_g": float(str(carbs[i] or 0)),
                            "fat_g": float(str(fats[i] or 0)),
                        }
                    )
                except ValueError:
                    continue
            if not items:
                est = request.session.get("ai_meal_estimate") or {}
                items = est.get("items") or []
            total_c = sum(int(it.get("calories") or 0) for it in items)
            total_p = round(sum(float(it.get("protein_g") or 0) for it in items), 1)
            total_k = round(sum(float(it.get("carbs_g") or 0) for it in items), 1)
            total_f = round(sum(float(it.get("fat_g") or 0) for it in items), 1)
            est = request.session.get("ai_meal_estimate") or {}
            payload = {
                "items": items,
                "confidence": est.get("confidence", 0.2),
                "notes": est.get("notes") or [],
                "provider": est.get("provider", "offline"),
                "fallback_used": est.get("fallback_used", False),
                "disclaimer": est.get("disclaimer", "Estimates only."),
                "total_calories": total_c,
                "total_protein": total_p,
                "total_carbs": total_k,
                "total_fat": total_f,
            }
            note = ai_assist.meal_estimate_to_note(payload)
            try:
                ai_assist.append_meal_note_to_checkin(session, note)
                session.commit()
                request.session.pop("ai_meal_estimate", None)
                _flash(request, "Meal estimate saved to today's check-in notes.", "success")
                return RedirectResponse("/checkins", status_code=303)
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                _flash(request, f"Save failed: {exc}", "error")
                return RedirectResponse("/ai/meal", status_code=303)

        _flash(request, "Unknown action.", "error")
        return RedirectResponse("/ai/meal", status_code=303)
    finally:
        session.close()


@router.get("/ai/equipment", response_class=HTMLResponse)
def ai_equipment_get(request: Request) -> HTMLResponse:
    session = _db()
    try:
        profile = svc.get_profile(session)
        estimate = request.session.get("ai_equipment_estimate")
        return templates.TemplateResponse(
            request,
            "ai_equipment.html",
            _base_ctx(
                request,
                page="ai",
                profile=profile,
                estimate=estimate,
                conf_level=_conf_badge(float((estimate or {}).get("confidence") or 0)),
                equipment_options=EQUIPMENT_OPTIONS,
                **_provider_ctx(session),
            ),
        )
    finally:
        session.close()


@router.post("/ai/equipment", response_model=None)
async def ai_equipment_post(
    request: Request,
    action: str = Form("estimate"),
    caption: str = Form(""),
    image: UploadFile | None = File(None),
):
    session = _db()
    try:
        if action == "discard":
            request.session.pop("ai_equipment_estimate", None)
            _flash(request, "Equipment preview discarded.", "info")
            return RedirectResponse("/ai/equipment", status_code=303)

        if action == "estimate":
            image_bytes, filename, err = await _read_upload(image)
            if err:
                _flash(request, err, "error")
                return RedirectResponse("/ai/equipment", status_code=303)
            result = ai_assist.estimate_equipment(
                session,
                image_bytes=image_bytes,
                filename=filename,
                caption=caption,
            )
            request.session["ai_equipment_estimate"] = result.as_dict()
            if result.fallback_used:
                _flash(request, "Remote provider unavailable — offline parse used.", "info")
            return RedirectResponse("/ai/equipment", status_code=303)

        if action == "apply":
            form = await request.form()
            equipment = [v for v in form.getlist("equipment") if v] or ["bodyweight"]
            try:
                ai_assist.apply_equipment(session, equipment, regenerate=True)
                session.commit()
                request.session.pop("ai_equipment_estimate", None)
                _flash(request, "Equipment applied and protocol regenerated.", "success")
                return RedirectResponse("/training", status_code=303)
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                _flash(request, f"Apply failed: {exc}", "error")
                return RedirectResponse("/ai/equipment", status_code=303)

        _flash(request, "Unknown action.", "error")
        return RedirectResponse("/ai/equipment", status_code=303)
    finally:
        session.close()


@router.get("/settings/ai", response_class=HTMLResponse)
def settings_ai_get(request: Request) -> HTMLResponse:
    session = _db()
    try:
        profile = svc.get_profile(session)
        cfg = ai_assist.resolve_ai_config(session)
        stored = ai_assist.get_settings_map(session)
        return templates.TemplateResponse(
            request,
            "settings_ai.html",
            _base_ctx(
                request,
                page="settings",
                profile=profile,
                ai_config=cfg.as_public_dict(),
                stored=stored,
                provider_label=cfg.label(),
            ),
        )
    finally:
        session.close()


@router.post("/settings/ai", response_model=None)
async def settings_ai_post(request: Request):
    form = await request.form()
    session = _db()
    try:
        provider = str(form.get("ai_provider") or "offline").strip().lower()
        if provider not in ("offline", "ollama", "openai_compatible"):
            provider = "offline"
        base_url = str(form.get("ai_base_url") or "").strip()
        model = str(form.get("ai_model") or "").strip()
        api_key = str(form.get("ai_api_key") or "").strip()
        clear_key = str(form.get("clear_api_key") or "") == "1"

        values = {
            "ai_provider": provider,
            "ai_base_url": base_url,
            "ai_model": model,
        }
        if clear_key:
            values["ai_api_key"] = ""
        elif api_key and not set(api_key) <= {"•", "•"} and "••••" not in api_key:
            values["ai_api_key"] = api_key
        # if blank / masked, leave existing key

        ai_assist.set_settings(session, values)
        session.commit()
        _flash(request, "AI settings saved (local SQLite). Env vars still override when set.", "success")
        return RedirectResponse("/settings/ai", status_code=303)
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        _flash(request, f"Save failed: {exc}", "error")
        return RedirectResponse("/settings/ai", status_code=303)
    finally:
        session.close()
