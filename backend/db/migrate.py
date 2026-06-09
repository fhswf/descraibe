"""Simple SQL migration runner for PostgreSQL.

Usage:
  AD_DATABASE_URL=postgresql://... uv run python -m backend.db.migrate
"""

from __future__ import annotations

import os
from pathlib import Path


def main() -> None:
    database_url = os.environ.get("AD_DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("AD_DATABASE_URL is required")

    try:
        import psycopg
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"psycopg is required: {exc}") from exc

    migrations_dir = Path(__file__).parent / "migrations"
    files = sorted(migrations_dir.glob("*.sql"))

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )

            for path in files:
                version = path.name
                cur.execute("SELECT 1 FROM schema_migrations WHERE version = %s", (version,))
                if cur.fetchone():
                    continue

                sql = path.read_text(encoding="utf-8")
                cur.execute(sql)
                cur.execute("INSERT INTO schema_migrations(version) VALUES (%s)", (version,))
                print(f"Applied migration {version}")

        conn.commit()


if __name__ == "__main__":
    main()
