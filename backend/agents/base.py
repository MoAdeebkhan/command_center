"""
Base agent class with Ollama llama4 integration.
All agents inherit from this and call self.ask_ollama() for AI tasks.
"""
import httpx
import json
import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)

OLLAMA_HOST = "http://10.10.0.130:11434"
OLLAMA_MODEL = "llama3:latest"
OLLAMA_TIMEOUT = 180  # seconds


class BaseAgent(ABC):
    name: str = "BaseAgent"

    def ask_ollama(
        self,
        prompt: str,
        system: str = "You are an expert BI migration assistant. Always respond with valid JSON when asked.",
        temperature: float = 0.2,
        expect_json: bool = True,
    ) -> str:
        """
        Send a prompt to Ollama llama4 and return the response string.
        Falls back gracefully if Ollama is unreachable.
        """
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": 4096,
            },
        }

        try:
            with httpx.Client(timeout=OLLAMA_TIMEOUT) as client:
                resp = client.post(f"{OLLAMA_HOST}/api/generate", json=payload)
                resp.raise_for_status()
                data = resp.json()
                raw = data.get("response", "")

                if expect_json:
                    # Try to extract JSON from the response
                    raw = self._extract_json(raw)

                return raw

        except httpx.TimeoutException:
            logger.warning(f"[{self.name}] Ollama timeout — using fallback")
            return json.dumps({"error": "timeout", "fallback": True})
        except Exception as e:
            logger.warning(f"[{self.name}] Ollama error: {e} — using fallback")
            return json.dumps({"error": str(e), "fallback": True})

    def _extract_json(self, text: str) -> str:
        """Extract JSON block from LLM response that may contain markdown fences."""
        text = text.strip()
        # Strip markdown code fences
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.rfind("```")
            if end > start:
                text = text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.rfind("```")
            if end > start:
                text = text[start:end].strip()
        return text

    def parse_json_safe(self, text: str, fallback: dict = None) -> dict:
        """Parse JSON safely, returning fallback on failure."""
        try:
            return json.loads(text)
        except Exception:
            return fallback or {}

    @abstractmethod
    def run(self, context: dict) -> dict:
        """
        Execute the agent's work.
        context: shared dict passed between agents in the pipeline.
        Returns updated context dict.
        """
        pass
