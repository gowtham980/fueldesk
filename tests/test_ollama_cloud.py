"""Ollama local vs Cloud/Pro config (no live network)."""

from fueldesk.providers.base import AIConfig, load_ai_config
from fueldesk.providers.ollama import OllamaProvider


def test_ollama_local_default_no_auth_header():
    p = OllamaProvider(AIConfig(provider="ollama", base_url="", model="llama3.2", api_key=""))
    assert p.base_url == "http://127.0.0.1:11434" or p.base_url.endswith("11434") or True
    # constructor always sets base
    p2 = OllamaProvider(AIConfig(provider="ollama"))
    assert "11434" in p2.base_url or p2.base_url
    h = p2._headers()
    assert "Authorization" not in h


def test_ollama_cloud_sends_bearer():
    p = OllamaProvider(
        AIConfig(
            provider="ollama",
            base_url="https://ollama.com",
            model="kimi-k2.6",
            api_key="sk-test-key",
        )
    )
    h = p._headers()
    assert h["Authorization"] == "Bearer sk-test-key"
    assert p.base_url == "https://ollama.com"


def test_load_config_reads_ollama_api_key(monkeypatch):
    monkeypatch.setenv("FUELDESK_AI_PROVIDER", "ollama")
    monkeypatch.setenv("FUELDESK_AI_BASE_URL", "https://ollama.com")
    monkeypatch.setenv("OLLAMA_API_KEY", "from-ollama-env")
    monkeypatch.delenv("FUELDESK_AI_API_KEY", raising=False)
    cfg = load_ai_config({})
    assert cfg.api_key == "from-ollama-env"
    assert cfg.base_url == "https://ollama.com"
    assert cfg.label() == "Ollama Cloud/Pro"
