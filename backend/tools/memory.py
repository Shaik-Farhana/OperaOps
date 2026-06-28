"""Memory tools — Hindsight recall and store."""

from hindsight_client import hindsight


async def recall_incidents(query: str, top_k: int = 3) -> dict:
    memories = await hindsight.recall_hybrid(query, top_k=top_k)
    faithfulness = 0.0
    if memories:
        faithfulness = min(memories[0].get("_score", 0) / 10.0, 0.95) if memories[0].get("_score", 0) > 1 else memories[0].get("_score", 0.5)
    return {
        "memories": memories,
        "count": len(memories),
        "faithfulness": faithfulness,
        "ids": [m.get("metadata", {}).get("incident_id", f"past_{i}") for i, m in enumerate(memories)],
    }


async def store_resolution(incident_id: str, content: str, metadata: dict) -> dict:
    return await hindsight.store(incident_id, content, metadata)
