"""Shared AI provider types, config loading, and factory."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Protocol

ProviderName = Literal["offline", "ollama", "openai_compatible", "gemini"]

KNOWN_EQUIPMENT = (
    "bodyweight",
    "dumbbells",
    "barbell",
    "machines",
    "bands",
    "kettlebell",
    "pullup_bar",
)


@dataclass
class AIConfig:
    provider: ProviderName = "offline"
    base_url: str = ""
    model: str = ""
    api_key: str = ""

    def label(self) -> str:
        if self.provider == "offline":
            return "Offline"
        if self.provider == "gemini":
            return "Gemini (ADK)"
        if self.provider == "ollama":
            host = (self.base_url or "").lower()
            if "ollama.com" in host:
                return "Ollama Cloud/Pro"
            return "Ollama"
        return "API"

    def as_public_dict(self) -> dict[str, Any]:
        """Safe for templates — mask API key."""
        key = self.api_key or ""
        masked = ""
        if key:
            if len(key) <= 8:
                masked = "••••" + key[-2:]
            else:
                masked = key[:3] + "••••" + key[-4:]
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "api_key_masked": masked,
            "has_api_key": bool(key),
            "label": self.label(),
        }


@dataclass
class ProfileParseResult:
    fields: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    notes: list[str] = field(default_factory=list)
    provider: str = "offline"
    fallback_used: bool = False
    raw_text: str = ""

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class MealItemEstimate:
    name: str
    calories: int
    protein_g: float
    carbs_g: float
    fat_g: float


@dataclass
class MealEstimate:
    items: list[MealItemEstimate] = field(default_factory=list)
    confidence: float = 0.0
    notes: list[str] = field(default_factory=list)
    provider: str = "offline"
    fallback_used: bool = False
    disclaimer: str = (
        "Estimates only — not medical nutrition analysis. Review and edit before logging."
    )

    @property
    def total_calories(self) -> int:
        return int(sum(i.calories for i in self.items))

    @property
    def total_protein(self) -> float:
        return round(sum(i.protein_g for i in self.items), 1)

    @property
    def total_carbs(self) -> float:
        return round(sum(i.carbs_g for i in self.items), 1)

    @property
    def total_fat(self) -> float:
        return round(sum(i.fat_g for i in self.items), 1)

    def as_dict(self) -> dict[str, Any]:
        return {
            "items": [asdict(i) for i in self.items],
            "confidence": self.confidence,
            "notes": self.notes,
            "provider": self.provider,
            "fallback_used": self.fallback_used,
            "disclaimer": self.disclaimer,
            "total_calories": self.total_calories,
            "total_protein": self.total_protein,
            "total_carbs": self.total_carbs,
            "total_fat": self.total_fat,
        }


@dataclass
class EquipmentEstimate:
    equipment: list[str] = field(default_factory=list)
    confidence: float = 0.0
    notes: list[str] = field(default_factory=list)
    provider: str = "offline"
    fallback_used: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class AIProvider(Protocol):
    name: str

    def parse_profile(self, text: str) -> ProfileParseResult: ...

    def estimate_meal(
        self,
        *,
        image_bytes: bytes | None = None,
        filename: str = "",
        caption: str = "",
    ) -> MealEstimate: ...

    def estimate_equipment(
        self,
        *,
        image_bytes: bytes | None = None,
        filename: str = "",
        caption: str = "",
    ) -> EquipmentEstimate: ...


def load_ai_config(settings: dict[str, str] | None = None) -> AIConfig:
    """Merge env vars over SQLite settings (env wins when set)."""
    settings = settings or {}
    provider = (
        os.environ.get("FUELDESK_AI_PROVIDER")
        or settings.get("ai_provider")
        or "offline"
    ).strip().lower()
    if provider not in ("offline", "ollama", "openai_compatible", "gemini"):
        provider = "offline"

    base_url = (
        os.environ.get("FUELDESK_AI_BASE_URL")
        or settings.get("ai_base_url")
        or ""
    ).strip()
    model = (
        os.environ.get("FUELDESK_AI_MODEL")
        or settings.get("ai_model")
        or ""
    ).strip()
    api_key = (
        os.environ.get("FUELDESK_AI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("OLLAMA_API_KEY")
        or settings.get("ai_api_key")
        or ""
    ).strip()

    if provider == "ollama" and not base_url:
        base_url = "http://127.0.0.1:11434"
    if provider == "ollama" and not model:
        model = "llama3.2"
    if provider == "openai_compatible" and not base_url:
        base_url = "https://api.openai.com/v1"
    if provider == "openai_compatible" and not model:
        model = "gpt-4o-mini"
    if provider == "gemini" and not model:
        model = "gemini-2.0-flash"

    return AIConfig(
        provider=provider,  # type: ignore[arg-type]
        base_url=base_url,
        model=model,
        api_key=api_key,
    )


def get_provider(config: AIConfig | None = None) -> AIProvider:
    """Return configured provider instance (never raises)."""
    cfg = config or load_ai_config()
    if cfg.provider == "ollama":
        from fueldesk.providers.ollama import OllamaProvider

        return OllamaProvider(cfg)
    if cfg.provider == "openai_compatible":
        from fueldesk.providers.openai_compat import OpenAICompatProvider

        return OpenAICompatProvider(cfg)
    # gemini structured assist uses offline heuristics for parse/meal/equip;
    # multi-turn coach uses ADK separately in services.adk_coach
    from fueldesk.providers.offline import OfflineProvider

    return OfflineProvider()
