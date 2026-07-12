"""Ollama HTTP provider (local). Falls back to offline on any failure."""

from __future__ import annotations

import base64
import json
import re
from typing import Any

import httpx

from fueldesk.providers.base import (
    AIConfig,
    EquipmentEstimate,
    MealEstimate,
    MealItemEstimate,
    ProfileParseResult,
)
from fueldesk.providers.offline import OfflineProvider

_offline = OfflineProvider()


def _extract_json(text: str) -> dict[str, Any] | list[Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start = text.find(open_c)
        end = text.rfind(close_c)
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    return None


class OllamaProvider:
    name = "ollama"

    def __init__(self, config: AIConfig) -> None:
        self.config = config
        self.base_url = (config.base_url or "http://127.0.0.1:11434").rstrip("/")
        self.model = config.model or "llama3.2"

    def _chat(
        self,
        prompt: str,
        *,
        images_b64: list[str] | None = None,
        timeout: float = 45.0,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "messages": [{"role": "user", "content": prompt}],
            "options": {"temperature": 0.1},
        }
        if images_b64:
            payload["messages"][0]["images"] = images_b64

        with httpx.Client(timeout=timeout) as client:
            try:
                r = client.post(f"{self.base_url}/api/chat", json=payload)
                r.raise_for_status()
                data = r.json()
                return (data.get("message") or {}).get("content") or data.get("response") or ""
            except Exception:
                gen: dict[str, Any] = {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1},
                }
                if images_b64:
                    gen["images"] = images_b64
                r = client.post(f"{self.base_url}/api/generate", json=gen)
                r.raise_for_status()
                return r.json().get("response") or ""

    def parse_profile(self, text: str) -> ProfileParseResult:
        base = _offline.parse_profile(text)
        prompt = (
            "Extract a fitness profile as strict JSON only (no markdown). Keys: "
            "sex (male|female), age (int), height_cm (float), weight_kg (float), "
            "activity_level (sedentary|light|moderate|active|very_active), "
            "goal (lose|maintain|gain), diet_flags (array of vegetarian|vegan|no_dairy|gluten_free), "
            "equipment (array of bodyweight|dumbbells|barbell|machines|bands|kettlebell|pullup_bar), "
            "days_per_week (1-7), experience (beginner|intermediate). Text:\n" + text
        )
        try:
            content = self._chat(prompt)
            data = _extract_json(content)
            if not isinstance(data, dict):
                base.fallback_used = True
                base.notes = list(base.notes) + ["Ollama response not JSON — used offline parse."]
                return base
            fields = dict(base.fields)
            for key in (
                "sex",
                "age",
                "height_cm",
                "weight_kg",
                "activity_level",
                "goal",
                "diet_flags",
                "equipment",
                "days_per_week",
                "experience",
            ):
                if key in data and data[key] not in (None, "", []):
                    fields[key] = data[key]
            fields["units"] = "metric"
            fields["notes"] = text[:500]
            return ProfileParseResult(
                fields=fields,
                confidence=min(0.9, max(base.confidence, 0.65)),
                notes=["Parsed with Ollama."] + list(base.notes[:2]),
                provider="ollama",
                raw_text=text,
            )
        except Exception as exc:  # noqa: BLE001
            base.fallback_used = True
            base.notes = list(base.notes) + [
                f"Ollama unavailable ({exc.__class__.__name__}) — offline fallback."
            ]
            return base

    def estimate_meal(
        self,
        *,
        image_bytes: bytes | None = None,
        filename: str = "",
        caption: str = "",
    ) -> MealEstimate:
        base = _offline.estimate_meal(
            image_bytes=image_bytes, filename=filename, caption=caption
        )
        prompt = (
            "Estimate foods on a plate as strict JSON: "
            '{"items":[{"name":str,"calories":int,"protein_g":float,"carbs_g":float,"fat_g":float}],'
            '"confidence":0-1}. Educational estimates only. Filename: '
            + filename
            + ". Caption: "
            + caption
            + "."
        )
        images = [base64.b64encode(image_bytes).decode("ascii")] if image_bytes else None
        try:
            content = self._chat(prompt, images_b64=images)
            data = _extract_json(content)
            if not isinstance(data, dict) or "items" not in data:
                base.fallback_used = True
                base.notes = list(base.notes) + ["Ollama meal response invalid — offline estimate."]
                return base
            items: list[MealItemEstimate] = []
            for raw in data.get("items") or []:
                if not isinstance(raw, dict):
                    continue
                items.append(
                    MealItemEstimate(
                        name=str(raw.get("name") or "Item"),
                        calories=int(raw.get("calories") or 0),
                        protein_g=float(raw.get("protein_g") or 0),
                        carbs_g=float(raw.get("carbs_g") or 0),
                        fat_g=float(raw.get("fat_g") or 0),
                    )
                )
            if not items:
                base.fallback_used = True
                return base
            conf = float(data.get("confidence") or 0.6)
            return MealEstimate(
                items=items,
                confidence=max(0.0, min(conf, 0.95)),
                notes=["Estimated with Ollama (vision if model supports images)."],
                provider="ollama",
            )
        except Exception as exc:  # noqa: BLE001
            base.fallback_used = True
            base.notes = list(base.notes) + [
                f"Ollama unavailable ({exc.__class__.__name__}) — offline estimate."
            ]
            return base

    def estimate_equipment(
        self,
        *,
        image_bytes: bytes | None = None,
        filename: str = "",
        caption: str = "",
    ) -> EquipmentEstimate:
        base = _offline.estimate_equipment(
            image_bytes=image_bytes, filename=filename, caption=caption
        )
        prompt = (
            "List gym equipment visible/described as strict JSON: "
            '{"equipment":["bodyweight"|"dumbbells"|"barbell"|"machines"|"bands"|"kettlebell"|"pullup_bar"],'
            '"confidence":0-1}. Filename: '
            + filename
            + ". Caption: "
            + caption
            + "."
        )
        images = [base64.b64encode(image_bytes).decode("ascii")] if image_bytes else None
        try:
            content = self._chat(prompt, images_b64=images)
            data = _extract_json(content)
            if not isinstance(data, dict):
                base.fallback_used = True
                base.notes = list(base.notes) + ["Ollama equipment response invalid — offline."]
                return base
            allowed = {
                "bodyweight",
                "dumbbells",
                "barbell",
                "machines",
                "bands",
                "kettlebell",
                "pullup_bar",
            }
            equip = [e for e in (data.get("equipment") or []) if e in allowed]
            if not equip and base.equipment:
                equip = list(base.equipment)
            conf = float(data.get("confidence") or (0.65 if equip else 0.2))
            return EquipmentEstimate(
                equipment=equip,
                confidence=max(0.0, min(conf, 0.95)),
                notes=["Estimated with Ollama."] + ([] if equip else list(base.notes)),
                provider="ollama",
            )
        except Exception as exc:  # noqa: BLE001
            base.fallback_used = True
            base.notes = list(base.notes) + [
                f"Ollama unavailable ({exc.__class__.__name__}) — offline fallback."
            ]
            return base
