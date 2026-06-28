"""
Load environment from project root .env.local (preferred) then .env (fallback).
"""

from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_env() -> None:
    """Load .env then .env.local so local overrides win."""
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(PROJECT_ROOT / ".env.local", override=True)


# Load on import so any module that imports this gets env vars
load_env()
