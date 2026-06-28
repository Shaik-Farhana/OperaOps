"""Vercel serverless entrypoint — re-exports the FastAPI app from backend/."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import env_loader  # noqa: F401 — loads env vars from project root

from main import app  # noqa: F401 — Vercel ASGI handler
