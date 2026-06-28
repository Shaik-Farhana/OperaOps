"""
hindsight_client.py
Wrapper around Hindsight API for storing and recalling incident memory.
Supports bank API (retain/recall/reflect) and legacy pipeline API.
"""

import os
import re
import httpx
from typing import Optional
import env_loader  # noqa: F401 — loads .env.local from project root

HINDSIGHT_API_KEY = os.getenv("HINDSIGHT_API_KEY")
HINDSIGHT_BANK_ID = os.getenv("HINDSIGHT_BANK_ID", "opera")
HINDSIGHT_PIPELINE_ID = os.getenv("HINDSIGHT_PIPELINE_ID")
HINDSIGHT_BASE_URL = os.getenv("HINDSIGHT_BASE_URL", "https://api.hindsight.vectorize.io")


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _bm25_style_score(query: str, content: str) -> float:
    """Lightweight keyword overlap scoring for hybrid recall."""
    q = _tokenize(query)
    c = _tokenize(content)
    if not q or not c:
        return 0.0
    overlap = len(q & c)
    return overlap / len(q)


class HindsightClient:
    def __init__(self):
        self.api_key = HINDSIGHT_API_KEY
        self.bank_id = HINDSIGHT_BANK_ID
        self.pipeline_id = HINDSIGHT_PIPELINE_ID
        self.base_url = HINDSIGHT_BASE_URL.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        self._use_bank_api = bool(
            self.api_key
            and self.bank_id
            and self.bank_id != "your_hindsight_bank_id_here"
        )
        self._use_pipeline_api = bool(
            self.api_key
            and self.pipeline_id
            and self.pipeline_id != "your_hindsight_pipeline_id_here"
            and not self._use_bank_api
        )
        self._mock_mode = not (self._use_bank_api or self._use_pipeline_api)
        if self._mock_mode:
            print("[Hindsight] Running in MOCK mode — set HINDSIGHT_API_KEY + HINDSIGHT_BANK_ID")
            self._mock_store: list[dict] = []
        elif self._use_bank_api:
            print(f"[Hindsight] Live bank mode — bank_id={self.bank_id}")

    @property
    def mode(self) -> str:
        if self._mock_mode:
            return "mock"
        if self._use_bank_api:
            return "bank"
        return "pipeline"

    def _normalize_bank_results(self, docs: list[dict]) -> list[dict]:
        normalized = []
        for doc in docs:
            content = doc.get("text") or doc.get("content", "")
            metadata = doc.get("metadata") or {}
            if doc.get("document_id") and "incident_id" not in metadata:
                metadata = {**metadata, "document_id": doc["document_id"]}
            normalized.append(
                {
                    "id": doc.get("id"),
                    "content": content,
                    "metadata": metadata,
                    "_score": doc.get("score", doc.get("_score", 0.5)),
                }
            )
        return normalized

    async def store(self, incident_id: str, content: str, metadata: dict) -> dict:
        if self._mock_mode:
            entry = {
                "id": f"mem_{incident_id}",
                "content": content,
                "metadata": metadata,
            }
            self._mock_store.append(entry)
            return {"status": "stored", "memory_id": entry["id"]}

        if self._use_bank_api:
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(
                        f"{self.base_url}/v1/default/banks/{self.bank_id}/memories",
                        headers=self.headers,
                        json={
                            "items": [
                                {
                                    "content": content,
                                    "context": f"incident:{incident_id}",
                                    "document_id": f"incident_{incident_id}",
                                    "metadata": {
                                        "incident_id": incident_id,
                                        "source": "operaops",
                                        **metadata,
                                    },
                                }
                            ],
                            "async": False,
                        },
                        timeout=30.0,
                    )
                    response.raise_for_status()
                    body = response.json()
                    return {
                        "status": "stored",
                        "bank_id": self.bank_id,
                        "items_count": body.get("items_count", 1),
                    }
                except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                    print(f"[Hindsight] store failed: {exc}")
                    return {"status": "degraded", "reason": "hindsight_store_failed"}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/pipelines/{self.pipeline_id}/documents",
                    headers=self.headers,
                    json={
                        "content": content,
                        "metadata": {
                            "incident_id": incident_id,
                            "source": "operaops",
                            **metadata,
                        },
                    },
                    timeout=15.0,
                )
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                print(f"[Hindsight] store failed: {exc}")
                return {"status": "degraded", "reason": "hindsight_store_failed"}

    async def recall(self, query: str, top_k: int = 3) -> list[dict]:
        return await self.recall_hybrid(query, top_k)

    async def recall_hybrid(self, query: str, top_k: int = 3) -> list[dict]:
        """Semantic recall + BM25-style keyword re-ranking."""
        if self._mock_mode:
            if not self._mock_store:
                return []
            matches = []
            query_lower = query.lower()
            for entry in self._mock_store:
                content = entry["content"]
                semantic_overlap = len(_tokenize(query_lower) & _tokenize(content.lower()))
                bm25 = _bm25_style_score(query, content)
                combined = semantic_overlap * 0.6 + bm25 * 10 * 0.4
                if combined > 1.5:
                    matches.append({**entry, "_score": combined})
            matches.sort(key=lambda x: x["_score"], reverse=True)
            return matches[:top_k]

        if self._use_bank_api:
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(
                        f"{self.base_url}/v1/default/banks/{self.bank_id}/memories/recall",
                        headers=self.headers,
                        json={"query": query, "max_tokens": 4096, "budget": "mid"},
                        timeout=20.0,
                    )
                    response.raise_for_status()
                    docs = self._normalize_bank_results(response.json().get("results", []))
                    for doc in docs:
                        bm25 = _bm25_style_score(query, doc.get("content", ""))
                        base = doc.get("_score", 0.5)
                        doc["_score"] = base * 0.7 + bm25 * 0.3
                    docs.sort(key=lambda x: x.get("_score", 0), reverse=True)
                    return docs[:top_k]
                except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                    print(f"[Hindsight] recall failed: {exc}")
                    return []

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/pipelines/{self.pipeline_id}/retrieve",
                    headers=self.headers,
                    json={"query": query, "top_k": top_k * 2},
                    timeout=15.0,
                )
                response.raise_for_status()
                docs = response.json().get("documents", [])
                for doc in docs:
                    content = doc.get("content", "")
                    bm25 = _bm25_style_score(query, content)
                    base = doc.get("score", doc.get("_score", 0.5))
                    doc["_score"] = base * 0.7 + bm25 * 0.3
                docs.sort(key=lambda x: x.get("_score", 0), reverse=True)
                return docs[:top_k]
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                print(f"[Hindsight] recall failed: {exc}")
                return []

    def compute_faithfulness(self, diagnosis: dict, memories: list[dict]) -> float:
        """
        Simplified RAGAS faithfulness: fraction of diagnosis claims found in memory.
        """
        if not memories:
            return 0.0

        memory_text = " ".join(m.get("content", "") for m in memories).lower()
        claims = [
            diagnosis.get("root_cause", ""),
            diagnosis.get("fix", "")[:200],
        ]
        supported = 0
        total = 0
        for claim in claims:
            if not claim:
                continue
            total += 1
            claim_words = _tokenize(claim)
            mem_words = _tokenize(memory_text)
            if claim_words and len(claim_words & mem_words) / len(claim_words) >= 0.3:
                supported += 1
            elif any(w in memory_text for w in list(claim_words)[:5]):
                supported += 1

        return supported / total if total else 0.0

    async def reflect(self, pattern_query: str) -> Optional[str]:
        if self._mock_mode:
            stored_count = len(self._mock_store)
            if stored_count >= 3:
                return (
                    f"Pattern detected across {stored_count} stored incidents: "
                    "recurring infrastructure issues suggest config drift or "
                    "missing env vars in deployment pipeline."
                )
            return None

        if self._use_bank_api:
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(
                        f"{self.base_url}/v1/default/banks/{self.bank_id}/reflect",
                        headers=self.headers,
                        json={"query": pattern_query, "budget": "low", "include_facts": True},
                        timeout=30.0,
                    )
                    response.raise_for_status()
                    body = response.json()
                    text = body.get("text") or body.get("response")
                    return text if text else None
                except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                    print(f"[Hindsight] reflect failed: {exc}")
                    return None

        memories = await self.recall(pattern_query, top_k=10)
        if len(memories) < 3:
            return None

        memory_text = "\n".join([f"- {m.get('content', '')[:200]}" for m in memories[:5]])
        return f"Recurring pattern found across {len(memories)} incidents:\n{memory_text}"


hindsight = HindsightClient()
