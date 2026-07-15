"""LLM client targeting the KPMG Workbench OpenAI-compatible gateway (API-key).

The same gateway fronts a GPT-4-class chat deployment and the embedding
deployment. When no Workbench credentials are configured (local dev), the
client reports `available = False` and callers fall back to deterministic,
non-AI behaviour so the app still runs offline and tests stay hermetic.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_FENCE = re.compile(r"^```[a-zA-Z]*\n?|\n?```$", re.MULTILINE)


class LLMUnavailable(RuntimeError):
    pass


def _extract_json(text: str) -> Any:
    """Parse JSON from a model response, tolerating code fences / stray prose."""
    cleaned = _FENCE.sub("", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Grab the first balanced {...} or [...] block.
        for opener, closer in (("{", "}"), ("[", "]")):
            start = cleaned.find(opener)
            end = cleaned.rfind(closer)
            if start != -1 and end > start:
                try:
                    return json.loads(cleaned[start : end + 1])
                except json.JSONDecodeError:
                    continue
        raise


class LLMClient:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self._client = None
        if self.settings.workbench_configured:
            try:
                from openai import OpenAI

                self._client = OpenAI(
                    base_url=self.settings.workbench_openai_base_url,
                    api_key=self.settings.workbench_openai_api_key,
                    default_query={"api-version": self.settings.workbench_api_version},
                )
            except Exception as exc:  # pragma: no cover
                logger.warning("LLM client init failed; running without LLM: %s", exc)
                self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        if not self.available:
            raise LLMUnavailable("Workbench LLM not configured")
        kwargs: dict[str, Any] = {
            "model": self.settings.chat_deployment,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.settings.llm_temperature if temperature is None else temperature,
            "max_tokens": self.settings.llm_max_tokens if max_tokens is None else max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = self._client.chat.completions.create(**kwargs)  # type: ignore[union-attr]
        return resp.choices[0].message.content or ""

    def chat_json(self, system: str, user: str, **kwargs: Any) -> Any:
        raw = self.chat(system, user, json_mode=True, **kwargs)
        return _extract_json(raw)
