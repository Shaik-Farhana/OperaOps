# OperaOps — AI Incident Response Agent

> An engineering incident response agent that learns from every outage, routes LLM calls intelligently, and gets measurably cheaper with each incident it resolves.

**Powered by [Hindsight](https://hindsight.vectorize.io/) (agent memory) + [cascadeflow](https://docs.cascadeflow.ai/) (runtime intelligence) + [Groq](https://groq.com/) (LLM)**

---

## What It Does

OperaOps is a production-ready incident response agent that:

- **Remembers every past incident** via [Hindsight agent memory](https://github.com/vectorize-io/hindsight) — each resolved incident is stored, and future incidents recall similar patterns
- **Routes LLM calls intelligently** via [cascadeflow](https://github.com/lemony-ai/cascadeflow) — cheap models for known patterns, strong models only for novel/critical incidents
- **Enforces per-incident budgets** — cascadeflow gracefully degrades to cheaper models before hitting the cap
- **Produces a full audit trail** — every model decision, cost, and latency is logged

## The Before / After

| | Incident #1 | Incident #5 |
|--|-------------|-------------|
| Memory context | None | 3 similar past incidents recalled |
| Model calls | 4 (all expensive) | 1 (cheap, memory-informed) |
| Cost | ~$0.0180 | ~$0.0030 |
| Response quality | Generic | Pinpoints known fix immediately |

---

## Stack

- **Frontend:** React + Vite + Tailwind CSS
- **Backend:** FastAPI (Python)
- **Memory:** [Hindsight Cloud](https://ui.hindsight.vectorize.io) by Vectorize
- **Runtime Intelligence:** [cascadeflow](https://docs.cascadeflow.ai/)
- **LLM:** Groq (qwen3-32b / llama-3.3-70b)
- **Database:** Supabase

---

## Setup

### 1. Clone & install

```bash
git clone https://github.com/YOUR_TEAM/operaops
cd operaops
```

### 2. Backend

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example .env
# Fill in your keys in .env
uvicorn main:app --reload
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

### 4. Environment variables

Copy `.env.example` to `.env` and fill in:

```env
GROQ_API_KEY=           # groq.com — free tier
HINDSIGHT_API_KEY=      # ui.hindsight.vectorize.io — use promo MEMHACK625 for $50 credit
HINDSIGHT_PIPELINE_ID=  # from Hindsight Cloud dashboard
SUPABASE_URL=           # optional, for production persistence
SUPABASE_ANON_KEY=      # optional
```

> **Note:** cascadeflow needs no API key — `pip install cascadeflow` is all it takes.

---

## How Hindsight Is Used

Every resolved incident is stored in Hindsight with:
- Error signature and stack trace summary
- Root cause identified by the agent
- Fix that was applied
- Resolution time and severity

On the next incident, the agent queries Hindsight with semantic search. Top-3 similar past incidents are injected into the agent's context, making the diagnosis faster and more accurate.

```python
# Store after resolution
await hindsight.store(incident_id, memory_content, metadata)

# Recall before diagnosis
memories = await hindsight.recall(query, top_k=3)
```

→ [Hindsight documentation](https://hindsight.vectorize.io/) | [Vectorize agent memory](https://vectorize.io/what-is-agent-memory)

---

## How cascadeflow Is Used

Every LLM call goes through cascadeflow's router:

```python
model, reason = cascade.select_model(
    incident_severity=incident["severity"],
    has_memory_match=has_memory,
    memory_confidence=memory_confidence,
    incident_budget_remaining=budget_left,
)
```

Routing rules:
- P1 + no memory → strong model (novel critical incident)
- P1 + high memory confidence → cheap model (known pattern)
- Budget < 20% → cheap model regardless
- Every decision is logged to the audit trail

→ [cascadeflow documentation](https://docs.cascadeflow.ai/) | [cascadeflow GitHub](https://github.com/lemony-ai/cascadeflow)

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/incidents/synthetic` | List all synthetic incidents |
| POST | `/incidents/trigger` | Trigger incident through agent pipeline |
| GET | `/incidents` | List all processed incidents |
| GET | `/costs/summary` | Session cost summary |
| GET | `/costs/audit` | Full cascadeflow audit trail |
| POST | `/demo/run-sequence` | Run 5-incident demo sequence |

---

## Architecture

```
Incident Input
     ↓
Hindsight Recall (top-3 similar past incidents)
     ↓
cascadeflow Route (select model + check budget)
     ↓
Groq LLM (diagnosis + RCA draft)
     ↓
cascadeflow Log (cost, latency, model, reason)
     ↓
Hindsight Store (save for future recall)
```

---

Built with ❤️ at HackwithHyderabad 2.0 — Microsoft Office, Hyderabad
