"""Conversation memory.

Redis/in-memory keeps the last N Q&A pairs for prompt continuity. Cosmos DB,
when configured, records every exchange for audit/lineage and retention controls.
"""
from __future__ import annotations

import json
from typing import Optional

from app.clients.audit_store import AuditStore, get_audit_store
from app.clients.cache import Cache, get_cache
from app.config import get_settings
from app.models.schemas import QAExchange

_TTL_S = 60 * 60 * 8  # 8h session window


class ConversationMemory:
    def __init__(self, cache: Optional[Cache] = None, audit: Optional[AuditStore] = None) -> None:
        self.cache = cache or get_cache()
        self.audit = audit or get_audit_store()
        self.window = get_settings().memory_window

    def _key(self, session_id: str) -> str:
        return f"tom:mem:{session_id}"

    def get(self, session_id: str) -> list[QAExchange]:
        raw = self.cache.get(self._key(session_id))
        if not raw:
            return []
        return [QAExchange(**x) for x in json.loads(raw)]

    def append(self, session_id: str, question: str, answer: str) -> None:
        history = self.get(session_id)
        history.append(QAExchange(question=question, answer=answer))
        history = history[-self.window :]
        self.cache.set(
            self._key(session_id),
            json.dumps([h.__dict__ for h in history]),
            ttl_s=_TTL_S,
        )
        self.audit.record_exchange(session_id, question, answer)

    def as_prompt_text(self, session_id: str) -> str:
        history = self.get(session_id)
        if not history:
            return "(no prior turns)"
        lines = []
        for i, qa in enumerate(history, 1):
            ans = qa.answer if len(qa.answer) <= 500 else qa.answer[:500] + "…"
            lines.append(f"Q{i}: {qa.question}\nA{i}: {ans}")
        return "\n".join(lines)
