# OperaOps — AI Incident Response Agent

> A demo app that simulates an on-call engineer: feed it fake production outages, get AI-suggested fixes, and watch it get cheaper when it has seen similar problems before.

**Stack:** React dashboard · FastAPI · [Hindsight](https://hindsight.vectorize.io/) memory · [cascadeflow](https://docs.cascadeflow.ai/) routing · [Groq](https://groq.com/) LLMs · Supabase

Built for **HackwithHyderabad 2.0**.

---

## What is this? (30 seconds)

When real software breaks (database full, API rate limit, bad deploy), engineers must figure out **what went wrong** and **how to fix it**.

**OperaOps does that with AI — using fake incidents for the demo:**

1. You pick a simulated outage from a catalog (~100+ incidents).
2. The agent recalls similar past ones from **memory** (Hindsight).
3. An **LLM** (Groq) writes root cause, fix, and confidence.
4. The dashboard shows **cost**, **latency**, and whether it **Diagnosed** or **Failed**.

It does **not** connect to live production systems. It is a **hackathon demo** showing smart AI routing + learning over time.

---

## Try it in the UI

1. Start backend + frontend (see [Setup](#setup) below).
2. Open **http://localhost:5173**
3. Pick an incident from the dropdown → **Trigger Incident**
4. Or click **Demo Sequence (×5)** — runs 5 incidents to show memory + cost improving on repeats

**How to read a result card:**

| UI element | Meaning |
|------------|---------|
| **Diagnosed** / **Failed** | Did the AI produce a valid fix? |
| **3 recalled** | Memory found 3 similar past incidents |
| **db_expert / api_expert** | Which domain router handled it |
| **Root cause / Suggested fix** | The AI answer |
| **$0.001x** | Cost of that LLM call |
| **Pattern analysis** | Optional long memory summary (click to expand) |

---

## The demo story

| | First time seeing an outage | After memory has learned |
|--|----------------------------|---------------------------|
| Memory | None | 3 similar incidents recalled |
| Model | Balanced / strong | Often cheaper tier |
| Cost | ~$0.001–0.004 | Can drop on repeats |
| Quality | Generic | Points at known fix patterns |

---

## Stack

| Layer | Technology |
|-------|------------|
| Frontend | React + Vite + Tailwind |
| Backend | FastAPI (Python) |
| Memory | Hindsight Cloud (`opera` bank) |
| Routing / budget | cascadeflow |
| LLM | Groq — `openai/gpt-oss-20b`, `llama-3.3-70b-versatile`, `openai/gpt-oss-120b` |
| Synthetic data | NeMo Data Designer (optional, `NVIDIA_API_KEY`) |
| Database | Supabase (migrations for persistence) |

---

## Setup

### 1. Clone & install

```bash
git clone <your-repo-url>
cd OperaOps
```

### 2. Environment

```bash
cp .env.example .env.local
# Fill in GROQ_API_KEY, HINDSIGHT_API_KEY, HINDSIGHT_BANK_ID=opera, Supabase vars
```

Secrets live in **`.env.local` only** — never commit it (see `.gitignore`).

### 3. Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API docs: **http://localhost:8000/docs**

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

App: **http://localhost:5173**

### 5. Migrations

```bash
# From repo root
python scripts/migrate.py --hindsight-only    # seed Hindsight memory bank
python scripts/migrate.py --supabase-only     # needs SUPABASE_DB_PASSWORD in .env.local
python scripts/migrate.py                     # both
```

### 6. Generate more incidents (optional)

```bash
pip install data-designer
python scripts/generate_incidents_nvidia.py --count 35 --merge
python scripts/migrate.py --hindsight-only --force
```

### 7. Test Groq

```bash
python scripts/test_groq.py
```

---

## Key environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `GROQ_API_KEY` | Yes | LLM diagnosis |
| `HINDSIGHT_API_KEY` | Yes | Agent memory |
| `HINDSIGHT_BANK_ID` | Yes | Memory bank (`opera`) |
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` | Optional | REST API |
| `SUPABASE_DB_PASSWORD` | For migrations | Postgres schema |
| `NVIDIA_API_KEY` | Optional | NeMo Data Designer + NIM |

See `.env.example` for the full list.

---

## Data files

| Path | Purpose |
|------|---------|
| `data/incidents.json` | Synthetic outage catalog (triggered in UI) |
| `data/runbooks.json` | Category playbooks (database, deployment, …) |
| `data/trajectories/` | Agent run logs (flywheel) |

---

## API endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Status, Hindsight mode, LLM config |
| GET | `/incidents/synthetic` | List incident catalog |
| POST | `/incidents/trigger` | Run one incident through agent |
| GET | `/incidents` | Session incident history |
| GET | `/costs/summary` | Session spend + MoE stats |
| GET | `/costs/audit` | Full routing audit log |
| GET | `/moe/stats` | Expert activations, fast-path hits |
| POST | `/eval/run` | Benchmark vs `incidents.json` |
| POST | `/demo/run-sequence` | 5-incident learning demo |

---

## Architecture (simplified)

```
Incident input
  → Parallel perceive (Hindsight recall + runbook + MoE expert)
  → Memory fast path? (high confidence → skip LLM)
  → Smart router (nano / balanced / strong Groq model)
  → ReAct loop (diagnose → validate → escalate if low confidence)
  → Guardrails → store in Hindsight → log trajectory
```

---

## Project layout

```
OperaOps/
├── backend/          # FastAPI agent (DECA-IR pipeline)
├── frontend/         # React dashboard
├── data/             # Incidents, runbooks, trajectories
├── scripts/          # migrate, generate data, test groq
├── supabase/         # SQL migrations
├── .env.example      # Template (safe to commit)
└── .env.local        # Your keys (gitignored)
```

---

## Security

- **Do not commit** `.env.local`, API keys, or private notes.
- Only **`README.md`** is tracked for markdown in this repo; other `.md` files stay local.
- Rotate any key that was ever pushed to a remote by mistake.

---

Built with ❤️ at HackwithHyderabad 2.0 — Microsoft Office, Hyderabad
