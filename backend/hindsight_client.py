"""
hindsight_client.py
Wrapper around Hindsight API for storing and recalling incident memory.
Hindsight docs: https://hindsight.vectorize.io/
Hindsight GitHub: https://github.com/vectorize-io/hindsight
"""

import os
import httpx
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

HINDSIGHT_API_KEY = os.getenv("HINDSIGHT_API_KEY")
HINDSIGHT_PIPELINE_ID = os.getenv("HINDSIGHT_PIPELINE_ID")
HINDSIGHT_BASE_URL = "https://api.hindsight.vectorize.io/v1"


class HindsightClient:
    """
    Thin wrapper around Hindsight Cloud REST API.
    Handles store, recall, and reflect operations for incident memory.
    """

    def __init__(self):
        self.api_key = HINDSIGHT_API_KEY
        self.pipeline_id = HINDSIGHT_PIPELINE_ID
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        self._mock_mode = not (self.api_key and self.pipeline_id)
        if self._mock_mode:
            print("[Hindsight] Running in MOCK mode — no API key/pipeline ID set")
            self._mock_store: list[dict] = []

    async def store(self, incident_id: str, content: str, metadata: dict) -> dict:
        """
        Store an incident resolution in Hindsight memory.
        Called after every resolved incident.
        """
        if self._mock_mode:
            entry = {
                "id": f"mem_{incident_id}",
                "content": content,
                "metadata": metadata,
            }
            self._mock_store.append(entry)
            return {"status": "stored", "memory_id": entry["id"]}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{HINDSIGHT_BASE_URL}/pipelines/{self.pipeline_id}/documents",
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
                print(f"[Hindsight] store failed, continuing without persistence: {exc}")
                return {"status": "degraded", "reason": "hindsight_store_failed"}

    async def recall(self, query: str, top_k: int = 3) -> list[dict]:
        """
        Recall similar past incidents from Hindsight memory.
        Returns top_k most semantically similar stored incidents.
        """
        if self._mock_mode:
            # Return mock memories that simulate real recall behavior
            if not self._mock_store:
                return []
            # Simple keyword match for mock mode
            matches = []
            query_lower = query.lower()
            for entry in self._mock_store:
                content_lower = entry["content"].lower()
                # Score by word overlap
                query_words = set(query_lower.split())
                content_words = set(content_lower.split())
                overlap = len(query_words & content_words)
                if overlap > 2:
                    matches.append({**entry, "_score": overlap})
            matches.sort(key=lambda x: x["_score"], reverse=True)
            return matches[:top_k]

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{HINDSIGHT_BASE_URL}/pipelines/{self.pipeline_id}/retrieve",
                    headers=self.headers,
                    json={"query": query, "top_k": top_k},
                    timeout=15.0,
                )
                response.raise_for_status()
                data = response.json()
                return data.get("documents", [])
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                print(f"[Hindsight] recall failed, falling back to no memory: {exc}")
                return []

    async def reflect(self, pattern_query: str) -> Optional[str]:
        """
        Ask Hindsight to reflect on recurring patterns in stored memory.
        Used to surface systemic issues across incidents.
        """
        if self._mock_mode:
            stored_count = len(self._mock_store)
            if stored_count >= 3:
                return (
                    f"Pattern detected across {stored_count} stored incidents: "
                    "recurring infrastructure issues suggest config drift or "
                    "missing env vars in deployment pipeline."
                )
            return None

        memories = await self.recall(pattern_query, top_k=10)
        if len(memories) < 3:
            return None

        # Build a reflection prompt from recalled memories
        memory_text = "\n".join(
            [f"- {m.get('content', '')[:200]}" for m in memories[:5]]
        )
        return f"Recurring pattern found across {len(memories)} incidents:\n{memory_text}"


# Singleton instance
hindsight = HindsightClient()
