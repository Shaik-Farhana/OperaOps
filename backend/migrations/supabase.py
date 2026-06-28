"""
Supabase migration runner — applies SQL files from supabase/migrations/.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import env_loader  # noqa: F401

MIGRATIONS_DIR = env_loader.PROJECT_ROOT / "supabase" / "migrations"

_POSTGRES_SCHEMES = ("postgresql://", "postgres://")


def _strip_env(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value or None


def _is_postgres_url(url: str | None) -> bool:
    if not url:
        return False
    lowered = url.lower()
    return lowered.startswith(_POSTGRES_SCHEMES)


def _database_url() -> str | None:
    # Prefer explicit Postgres URLs; ignore REST API URLs mistakenly set here.
    candidates = [
        _strip_env(os.getenv("SUPABASE_DATABASE_URL")),
        _strip_env(os.getenv("POSTGRES_URL_NON_POOLING")),
        _strip_env(os.getenv("POSTGRES_URL")),
        _strip_env(os.getenv("POSTGRES_PRISMA_URL")),
        _strip_env(os.getenv("DATABASE_URL")),
    ]
    for candidate in candidates:
        if _is_postgres_url(candidate):
            return candidate

    password = _strip_env(os.getenv("SUPABASE_DB_PASSWORD"))
    host = _strip_env(os.getenv("POSTGRES_HOST"))
    user = _strip_env(os.getenv("POSTGRES_USER")) or "postgres"
    dbname = _strip_env(os.getenv("POSTGRES_DATABASE")) or "postgres"
    port = _strip_env(os.getenv("POSTGRES_PORT")) or "5432"

    if password and host:
        return f"postgresql://{user}:{password}@{host}:{port}/{dbname}?sslmode=require"

    url = _strip_env(os.getenv("SUPABASE_URL")) or ""
    match = re.search(r"https://([^.]+)\.supabase\.co", url)
    if password and match:
        project_ref = match.group(1)
        host = _strip_env(os.getenv("SUPABASE_DB_HOST")) or f"db.{project_ref}.supabase.co"
        port = _strip_env(os.getenv("SUPABASE_DB_PORT")) or "5432"
        user = _strip_env(os.getenv("SUPABASE_DB_USER")) or "postgres"
        dbname = _strip_env(os.getenv("SUPABASE_DB_NAME")) or "postgres"
        return f"postgresql://{user}:{password}@{host}:{port}/{dbname}?sslmode=require"

    return None


def _applied_versions(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select version from public.schema_migrations
            """
        )
        return {row[0] for row in cur.fetchall()}


def run() -> dict:
    db_url = _database_url()
    if not db_url:
        return {
            "status": "skipped",
            "reason": "Set SUPABASE_DATABASE_URL or SUPABASE_DB_PASSWORD in .env.local",
            "migration_dir": str(MIGRATIONS_DIR),
        }

    try:
        import psycopg
    except ImportError:
        return {
            "status": "error",
            "reason": "Install psycopg: pip install 'psycopg[binary]'",
        }

    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        return {"status": "skipped", "reason": "No migration files found"}

    applied: list[str] = []
    with psycopg.connect(db_url) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """
                create table if not exists public.schema_migrations (
                  version text primary key,
                  applied_at timestamptz not null default now()
                )
                """
            )

        try:
            done = _applied_versions(conn)
        except Exception:
            done = set()

        for path in files:
            version = path.stem.split("_", 1)[0]
            if version in done:
                continue
            sql = path.read_text(encoding="utf-8")
            with conn.cursor() as cur:
                cur.execute(sql)
            applied.append(path.name)

    return {
        "status": "ok",
        "applied": applied,
        "migration_dir": str(MIGRATIONS_DIR),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(run(), indent=2))
