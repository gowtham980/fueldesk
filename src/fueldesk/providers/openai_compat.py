"""OpenAI-compatible HTTP provider. Falls back to offline on any failure."""

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


class OpenAICompatProvider:
    name = "openai_compatible"

    def __init__(self, config: AIConfig) -> None:
        self.config = config
        self.base_url = (config.base_url or "https://api.openai.com/v1").rstrip("/")
        self.model = config.model or "gpt-4o-mini"
        self.api_key = config.api_key or ""

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _chat(self, messages: list[dict[str, Any]], *, timeout: float = 60.0) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
        }
        with httpx.Client(timeout=timeout) as client:
            r = client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
            choices = data.get("choices") or []
            if not choices:
                return ""
            return (choices[0].get("message") or {}).get("content") or ""

    def parse_profile(self, text: str) -> ProfileParseResult:
        base = _offline.parse_profile(text)
        if not self.api_key and "openai.com" in self.base_url:
            base.fallback_used = True
            base.notes = list(base.notes) + ["No API key — offline parse."]
            return base
        prompt = (
            "Extract a fitness profile as strict JSON only. Keys: "
            "sex (male|female), age (int), height_cm (float), weight_kg (float), "
            "activity_level (sedentary|light|moderate|active|very_active), "
            "goal (lose|maintain|gain), diet_flags (array), "
            "equipment (array of bodyweight|dumbbells|barbell|machines|bands|kettlebell|pullup_bar), "
            "days_per_week (1-7), experience (beginner|intermediate). Text:\n" + text
        )
        try:
            content = self._chat(
                [
                    {"role": "system", "content": "You output only valid JSON."},
                    {"role": "user", "content": prompt},
                ]
            )
            data = _extract_json(content)
            if not isinstance(data, dict):
                base.fallback_used = True
                base.notes = list(base.notes) + ["API response not JSON — offline parse."]
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
                confidence=min(0.92, max(base.confidence, 0.7)),
                notes=["Parsed with OpenAI-compatible API."],
                provider="openai_compatible",
                raw_text=text,
            )
        except Exception as exc:  # noqa: BLE001
            base.fallback_used = True
            base.notes = list(base.notes) + [
                f"API unavailable ({exc.__class__.__name__}) — offline fallback."
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
        if not self.api_key and "openai.com" in self.base_url:
            base.fallback_used = True
            base.notes = list(base.notes) + ["No API key — offline meal estimate."]
            return base

        text_part = (
            "Estimate foods as strict JSON: "
            '{"items":[{"name":str,"calories":int,"protein_g":float,"carbs_g":float,"fat_g":float}],'
            '"confidence":0-1}. Filename: '
            + filename
            + ". Caption: "
            + caption
            + ". Estimates only."
        )
        if image_bytes:
            b64 = base64.b64encode(image_bytes).decode("ascii")
            mime = "image/jpeg"
            if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
                mime = "image/png"
            elif image_bytes[:4] == b"RIFF":
                mime = "image/webp"
            user_content: list[dict[str, Any]] | str = [
                {"type": "text", "text": text_part},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                },
            ]
        else:
            user_content = text_part

        try:
            content = self._chat(
                [
                    {
                        "role": "system",
                        "content": "You output only valid JSON. Educational estimates only.",
                    },
                    {"role": "user", "content": user_content},
                ]
            )
            data = _extract_json(content)
            if not isinstance(data, dict) or "items" not in data:
                base.fallback_used = True
                base.notes = list(base.notes) + ["API meal response invalid — offline."]
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
            conf = float(data.get("confidence") or 0.7)
            return MealEstimate(
                items=items,
                confidence=max(0.0, min(conf, 0.95)),
                notes=["Estimated with OpenAI-compatible vision/API."],
                provider="openai_compatible",
            )
        except Exception as exc:  # noqa: BLE001
            base.fallback_used = True
            base.notes = list(base.notes) + [
                f"API unavailable ({exc.__class__.__name__}) — offline estimate."
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
        if not self.api_key and "openai.com" in self.base_url:
            base.fallback_used = True
            base.notes = list(base.notes) + ["No API key — offline equipment parse."]
            return base

        text_part = (
            "List gym equipment as strict JSON: "
            '{"equipment":["bodyweight"|"dumbbells"|"barbell"|"machines"|"bands"|"kettlebell"|"pullup_bar"],'
            '"confidence":0-1}. Filename: '
            + filename
            + ". Caption: "
            + caption
            + "."
        )
        if image_bytes:
            b64 = base64.b64encode(image_bytes).decode("ascii")
            mime = "image/jpeg"
            if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
                mime = "image/png"
            user_content: list[dict[str, Any]] | str = [
                {"type": "text", "text": text_part},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                },
            ]
        else:
            user_content = text_part

        try:
            content = self._chat(
                [
                    {"role": "system", "content": "You output only valid JSON."},
                    {"role": "user", "content": user_content},
                ]
            )
            data = _extract_json(content)
            if not isinstance(data, dict):
                base.fallback_used = True
                base.notes = list(base.notes) + ["API equipment response invalid — offline."]
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
            conf = float(data.get("confidence") or (0.7 if equip else 0.2))
            return EquipmentEstimate(
                equipment=equip,
                confidence=max(0.0, min(conf, 0.95)),
                notes=["Estimated with OpenAI-compatible API."],
                provider="openai_compatible",
            )
        except Exception as exc:  # noqa: BLE001
            base.fallback_used = True
            base.notes = list(base.notes) + [
                f"API unavailable ({exc.__class__.__name__}) — offline fallback."
            ]
            return base
