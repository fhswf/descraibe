"""Relational data store with file fallback for user config and presets."""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Optional


class DataStore:
    def __init__(self, database_url: str, user_config_dir: Path, logger: logging.Logger):
        self.database_url = (database_url or "").strip()
        self.user_config_dir = Path(user_config_dir)
        self.logger = logger
        self._psycopg = None

        if self.database_url:
            try:
                import psycopg

                self._psycopg = psycopg
                self.logger.info("Relational datastore enabled")
            except Exception as exc:
                self.logger.warning("Failed to load psycopg, falling back to file store: %s", exc)

    @property
    def enabled(self) -> bool:
        return bool(self.database_url and self._psycopg)

    @staticmethod
    def safe_user_id(user: dict[str, Any]) -> str:
        issuer = str(user.get("iss", "")).strip()
        subject = str(user.get("sub", "")).strip()
        return hashlib.sha256(f"{issuer}|{subject}".encode("utf-8")).hexdigest()

    def _user_config_path(self, user: dict[str, Any]) -> Path:
        return self.user_config_dir / self.safe_user_id(user) / "config.json"

    def _read_user_config_file(self, user: dict[str, Any]) -> Optional[dict[str, Any]]:
        path = self._user_config_path(user)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else None
        except Exception:
            self.logger.warning("Could not parse user config at %s", path)
            return None

    def _write_user_config_file(self, user: dict[str, Any], payload: dict[str, Any]) -> None:
        path = self._user_config_path(user)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    def _touch_user(self, cur, user: dict[str, Any]) -> str:
        user_id = self.safe_user_id(user)
        cur.execute(
            """
            INSERT INTO app_users (
                id, issuer, subject, name, email, preferred_username, picture, updated_at, last_seen_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, now(), now())
            ON CONFLICT (id)
            DO UPDATE SET
                name = EXCLUDED.name,
                email = EXCLUDED.email,
                preferred_username = EXCLUDED.preferred_username,
                picture = EXCLUDED.picture,
                updated_at = now(),
                last_seen_at = now()
            """,
            (
                user_id,
                str(user.get("iss", "")).strip(),
                str(user.get("sub", "")).strip(),
                user.get("name"),
                user.get("email"),
                user.get("preferred_username"),
                user.get("picture"),
            ),
        )
        return user_id

    def get_user_config(self, user: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            return self._read_user_config_file(user) or {}

        try:
            with self._psycopg.connect(self.database_url) as conn:
                with conn.cursor() as cur:
                    user_id = self._touch_user(cur, user)
                    cur.execute(
                        "SELECT config, EXTRACT(EPOCH FROM updated_at)::bigint FROM user_configs WHERE user_id = %s",
                        (user_id,),
                    )
                    row = cur.fetchone()
                    conn.commit()
            if not row:
                return {}
            config, updated_at = row
            return {
                "config": config if isinstance(config, dict) else {},
                "updated_at": int(updated_at) if updated_at is not None else None,
            }
        except Exception as exc:
            self.logger.warning("DB get_user_config failed, using file fallback: %s", exc)
            return self._read_user_config_file(user) or {}

    def put_user_config(self, user: dict[str, Any], config: dict[str, Any]) -> int:
        payload = {
            "config": config,
            "updated_at": int(time.time()),
        }

        if not self.enabled:
            self._write_user_config_file(user, payload)
            return payload["updated_at"]

        try:
            encoded = json.dumps(config, ensure_ascii=False)
            with self._psycopg.connect(self.database_url) as conn:
                with conn.cursor() as cur:
                    user_id = self._touch_user(cur, user)
                    cur.execute(
                        """
                        INSERT INTO user_configs(user_id, config, updated_at)
                        VALUES (%s, %s::jsonb, now())
                        ON CONFLICT (user_id)
                        DO UPDATE SET config = EXCLUDED.config, updated_at = now()
                        RETURNING EXTRACT(EPOCH FROM updated_at)::bigint
                        """,
                        (user_id, encoded),
                    )
                    updated_at = int(cur.fetchone()[0])
                    conn.commit()
            return updated_at
        except Exception as exc:
            self.logger.warning("DB put_user_config failed, using file fallback: %s", exc)
            self._write_user_config_file(user, payload)
            return payload["updated_at"]

    def list_presets(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.enabled:
            payload = self._read_user_config_file(user) or {}
            config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
            presets = config.get("presets") if isinstance(config.get("presets"), list) else []
            return [p for p in presets if isinstance(p, dict)]

        with self._psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                user_id = self._touch_user(cur, user)
                cur.execute(
                    """
                    SELECT id, name, job_type, description, settings, is_default,
                           EXTRACT(EPOCH FROM created_at)::bigint,
                           EXTRACT(EPOCH FROM updated_at)::bigint
                    FROM ad_presets
                    WHERE user_id = %s
                    ORDER BY job_type, name
                    """,
                    (user_id,),
                )
                rows = cur.fetchall()
                conn.commit()

        return [
            {
                "id": row[0],
                "name": row[1],
                "job_type": row[2],
                "description": row[3],
                "settings": row[4] if isinstance(row[4], dict) else {},
                "is_default": bool(row[5]),
                "created_at": int(row[6]) if row[6] is not None else None,
                "updated_at": int(row[7]) if row[7] is not None else None,
            }
            for row in rows
        ]

    def create_preset(self, user: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
        preset_id = str(uuid.uuid4())
        name = str(data.get("name", "")).strip()
        if not name:
            raise ValueError("Preset name is required")

        job_type = str(data.get("job_type", "general")).strip() or "general"
        description = data.get("description")
        settings = data.get("settings") if isinstance(data.get("settings"), dict) else {}
        is_default = bool(data.get("is_default", False))

        if not self.enabled:
            payload = self._read_user_config_file(user) or {}
            cfg = payload.get("config") if isinstance(payload.get("config"), dict) else {}
            presets = cfg.get("presets") if isinstance(cfg.get("presets"), list) else []
            now_ts = int(time.time())

            if is_default:
                for preset in presets:
                    if isinstance(preset, dict) and str(preset.get("job_type", "general")) == job_type:
                        preset["is_default"] = False

            preset = {
                "id": preset_id,
                "name": name,
                "job_type": job_type,
                "description": description,
                "settings": settings,
                "is_default": is_default,
                "created_at": now_ts,
                "updated_at": now_ts,
            }
            presets.append(preset)
            cfg["presets"] = presets
            payload["config"] = cfg
            payload["updated_at"] = now_ts
            self._write_user_config_file(user, payload)
            return preset

        encoded_settings = json.dumps(settings, ensure_ascii=False)

        with self._psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                user_id = self._touch_user(cur, user)
                if is_default:
                    cur.execute(
                        "UPDATE ad_presets SET is_default = FALSE, updated_at = now() WHERE user_id = %s AND job_type = %s",
                        (user_id, job_type),
                    )

                cur.execute(
                    """
                    INSERT INTO ad_presets(id, user_id, name, job_type, description, settings, is_default, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, now(), now())
                    RETURNING EXTRACT(EPOCH FROM created_at)::bigint, EXTRACT(EPOCH FROM updated_at)::bigint
                    """,
                    (preset_id, user_id, name, job_type, description, encoded_settings, is_default),
                )
                created_at, updated_at = cur.fetchone()
                conn.commit()

        return {
            "id": preset_id,
            "name": name,
            "job_type": job_type,
            "description": description,
            "settings": settings,
            "is_default": is_default,
            "created_at": int(created_at),
            "updated_at": int(updated_at),
        }

    def update_preset(self, user: dict[str, Any], preset_id: str, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        if not preset_id:
            return None

        if not self.enabled:
            payload = self._read_user_config_file(user) or {}
            cfg = payload.get("config") if isinstance(payload.get("config"), dict) else {}
            presets = cfg.get("presets") if isinstance(cfg.get("presets"), list) else []
            now_ts = int(time.time())

            target = None
            for preset in presets:
                if isinstance(preset, dict) and preset.get("id") == preset_id:
                    target = preset
                    break
            if target is None:
                return None

            if "name" in data:
                target["name"] = str(data.get("name", "")).strip() or target.get("name")
            if "job_type" in data:
                target["job_type"] = str(data.get("job_type", "general")).strip() or "general"
            if "description" in data:
                target["description"] = data.get("description")
            if "settings" in data and isinstance(data.get("settings"), dict):
                target["settings"] = data.get("settings")
            if "is_default" in data:
                target["is_default"] = bool(data.get("is_default"))
                if target["is_default"]:
                    for preset in presets:
                        if (
                            isinstance(preset, dict)
                            and preset.get("id") != preset_id
                            and str(preset.get("job_type", "general")) == str(target.get("job_type", "general"))
                        ):
                            preset["is_default"] = False

            target["updated_at"] = now_ts
            cfg["presets"] = presets
            payload["config"] = cfg
            payload["updated_at"] = now_ts
            self._write_user_config_file(user, payload)
            return target

        with self._psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                user_id = self._touch_user(cur, user)

                cur.execute(
                    "SELECT id, name, job_type, description, settings, is_default FROM ad_presets WHERE id = %s AND user_id = %s",
                    (preset_id, user_id),
                )
                row = cur.fetchone()
                if not row:
                    conn.commit()
                    return None

                name = str(data.get("name", row[1])).strip() or row[1]
                job_type = str(data.get("job_type", row[2])).strip() or row[2]
                description = data.get("description", row[3])
                settings = data.get("settings", row[4]) if isinstance(data.get("settings", row[4]), dict) else (row[4] or {})
                is_default = bool(data.get("is_default", row[5]))

                if is_default:
                    cur.execute(
                        "UPDATE ad_presets SET is_default = FALSE, updated_at = now() WHERE user_id = %s AND job_type = %s AND id <> %s",
                        (user_id, job_type, preset_id),
                    )

                cur.execute(
                    """
                    UPDATE ad_presets
                    SET name = %s,
                        job_type = %s,
                        description = %s,
                        settings = %s::jsonb,
                        is_default = %s,
                        updated_at = now()
                    WHERE id = %s AND user_id = %s
                    RETURNING EXTRACT(EPOCH FROM created_at)::bigint, EXTRACT(EPOCH FROM updated_at)::bigint
                    """,
                    (name, job_type, description, json.dumps(settings, ensure_ascii=False), is_default, preset_id, user_id),
                )
                created_at, updated_at = cur.fetchone()
                conn.commit()

        return {
            "id": preset_id,
            "name": name,
            "job_type": job_type,
            "description": description,
            "settings": settings,
            "is_default": is_default,
            "created_at": int(created_at),
            "updated_at": int(updated_at),
        }

    def delete_preset(self, user: dict[str, Any], preset_id: str) -> bool:
        if not preset_id:
            return False

        if not self.enabled:
            payload = self._read_user_config_file(user) or {}
            cfg = payload.get("config") if isinstance(payload.get("config"), dict) else {}
            presets = cfg.get("presets") if isinstance(cfg.get("presets"), list) else []
            next_presets = [p for p in presets if not (isinstance(p, dict) and p.get("id") == preset_id)]
            if len(next_presets) == len(presets):
                return False
            cfg["presets"] = next_presets
            payload["config"] = cfg
            payload["updated_at"] = int(time.time())
            self._write_user_config_file(user, payload)
            return True

        with self._psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                user_id = self._touch_user(cur, user)
                cur.execute("DELETE FROM ad_presets WHERE id = %s AND user_id = %s", (preset_id, user_id))
                deleted = cur.rowcount > 0
                conn.commit()
                return deleted

    # ── Person storage ─────────────────────────────────────────────────────────

    def store_persons(self, job_id: str, persons_list: list[dict[str, Any]]) -> None:
        """Store or update person records for a job."""
        if not job_id:
            return

        if not self.enabled:
            self.logger.debug("DB not enabled, persons stored in Parquet only")
            return

        try:
            with self._psycopg.connect(self.database_url) as conn:
                with conn.cursor() as cur:
                    if persons_list:
                        keep_ids = [int(p.get("person_id", 0)) for p in persons_list]
                        placeholders = ",".join(["%s"] * len(keep_ids))
                        cur.execute(
                            f"DELETE FROM job_persons WHERE job_id = %s AND person_id NOT IN ({placeholders})",
                            [job_id] + keep_ids,
                        )
                    else:
                        cur.execute(
                            "DELETE FROM job_persons WHERE job_id = %s",
                            (job_id,),
                        )

                    for person in persons_list:
                        attributes_json = json.dumps(person.get("attributes") or {}, ensure_ascii=False)
                        appearances_json = json.dumps(person.get("appearances") or [], ensure_ascii=False)
                        cur.execute(
                            """
                            INSERT INTO job_persons (
                                job_id, person_id, name, attributes,
                                first_seen_ts, last_seen_ts, description, appearances
                            ) VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s::jsonb)
                            ON CONFLICT (job_id, person_id) DO UPDATE SET
                                name = EXCLUDED.name,
                                attributes = EXCLUDED.attributes,
                                last_seen_ts = EXCLUDED.last_seen_ts,
                                description = EXCLUDED.description,
                                appearances = EXCLUDED.appearances
                            """,
                            (
                                job_id,
                                int(person.get("person_id", 0)),
                                person.get("name"),
                                attributes_json,
                                float(person.get("first_seen_ts", 0.0)),
                                float(person.get("last_seen_ts", 0.0)),
                                person.get("description"),
                                appearances_json,
                            ),
                        )
                    conn.commit()
            self.logger.info("Stored %d persons for job %s", len(persons_list), job_id)
        except Exception as exc:
            self.logger.warning("DB store_persons failed: %s", exc)

    def get_persons(self, job_id: str) -> list[dict[str, Any]]:
        """Retrieve person records for a job."""
        if not job_id:
            return []

        if not self.enabled:
            return []

        try:
            with self._psycopg.connect(self.database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT person_id, name, attributes, first_seen_ts, last_seen_ts,
                               description, appearances
                        FROM job_persons
                        WHERE job_id = %s
                        ORDER BY person_id
                        """,
                        (job_id,),
                    )
                    rows = cur.fetchall()
                    conn.commit()

            return [
                {
                    "person_id": row[0],
                    "name": row[1],
                    "attributes": row[2] if isinstance(row[2], dict) else {},
                    "first_seen_ts": float(row[3]) if row[3] is not None else 0.0,
                    "last_seen_ts": float(row[4]) if row[4] is not None else 0.0,
                    "description": row[5],
                    "appearances": row[6] if isinstance(row[6], list) else [],
                }
                for row in rows
            ]
        except Exception as exc:
            self.logger.warning("DB get_persons failed: %s", exc)
            return []
