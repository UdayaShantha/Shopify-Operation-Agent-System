"""
llm/provider.py
Multi-LLM provider interface.
Supports:
  - Ollama (llama3 )  - primary llm
  - Gemini 1.5 Flash (via google-generativeai) - secondary LLM
  

The ACTIVE_PROVIDERS dict maps agent names to provider keys.
Override via environment variables:
  LISTING_PROVIDER=ollama
  QA_PROVIDER=gemini
  REPORTER_PROVIDER=ollama
"""

from __future__ import annotations
import os, json, time, logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)

# Which provider each LLM agent uses 
ACTIVE_PROVIDERS: dict[str, str] = {
    "listing":  os.getenv("LISTING_PROVIDER",  "ollama"),
    "qa":       os.getenv("QA_PROVIDER",        "gemini"),
    "reporter": os.getenv("REPORTER_PROVIDER",  "ollama"),
}

# Base class 
class LLMProvider(ABC):
    """Abstract LLM provider."""

    @abstractmethod
    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        """Return a text completion."""

    def complete_json(self, system: str, user: str, max_tokens: int = 1024) -> dict | list:
        """Return a parsed JSON completion (retries once on parse failure)."""
        for attempt in range(2):
            raw = self.complete(system, user + "\n\nRespond with valid JSON only. No markdown fences.", max_tokens)
            # Strip optional ```json ... ``` fences
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
                cleaned = cleaned.rsplit("```", 1)[0]
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError as e:
                logger.warning("JSON parse failed (attempt %d): %s", attempt + 1, e)
                if attempt == 1:
                    raise ValueError(f"LLM returned invalid JSON after 2 attempts.\nRaw:\n{raw}") from e

# Google Gemini 
class GeminiProvider(LLMProvider):
    MODEL = "gemini-1.5-flash"

    def __init__(self):
        import google.generativeai as genai  # type: ignore
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        self._model = genai.GenerativeModel(
            self.MODEL,
            generation_config={"temperature": 0.4},
        )

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        prompt = f"{system}\n\n{user}"
        resp = self._model.generate_content(
            prompt,
            generation_config={"max_output_tokens": max_tokens},
        )
        return resp.text


#  Ollama (local)
class OllamaProvider(LLMProvider):
    """Calls a locally running Ollama server (http://localhost:11434)."""

    def __init__(self, model: str = "llama3"):
        import requests  # type: ignore
        self._requests = requests
        self._model = model
        self._base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        resp = self._requests.post(f"{self._base}/api/chat", json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()["message"]["content"]


#  Mock provider (used when no API key is available) 
class MockProvider(LLMProvider):
    """
    Deterministic mock - used in CI / offline runs.
    Returns minimal but structurally valid JSON so the pipeline can complete.
    """

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        if "listing" in system.lower() or "title" in user.lower():
            return json.dumps([
                {
                    "supplier_sku": "MOCK_SKU",
                    "title": "Mock Product Title",
                    "bullets": ["Feature one", "Feature two", "Feature three"],
                    "description": "This is a mock product description for testing purposes.",
                    "tags": ["mock", "test", "product"],
                    "seo_title": "Mock Product - Best Quality | Shop Now",
                    "seo_description": "Buy the best Mock Product. Top quality, fast shipping.",
                }
            ])
        if "qa" in system.lower() or "redline" in user.lower():
            return json.dumps([
                {
                    "supplier_sku": "MOCK_SKU",
                    "issues": [],
                    "verdict": "PASS",
                    "notes": "No issues detected (mock QA).",
                }
            ])
        return json.dumps({"result": "mock"})


# Factory 
def get_provider(agent_name: str) -> LLMProvider:
    """
    Return an instantiated LLM provider for the given agent.
    Falls back to MockProvider if credentials are missing.
    """
    key = ACTIVE_PROVIDERS.get(agent_name, "anthropic")
    try:
        if key == "gemini":
            if not os.getenv("GEMINI_API_KEY"):
                raise EnvironmentError("GEMINI_API_KEY not set")
            return GeminiProvider()
        elif key == "ollama":
            model = os.getenv("OLLAMA_MODEL", "llama3")
            return OllamaProvider(model=model)
        else:
            raise ValueError(f"Unknown provider key: {key}")
    except (EnvironmentError, ImportError) as exc:
        logger.warning("Provider '%s' unavailable (%s). Falling back to MockProvider.", key, exc)
        return MockProvider()
