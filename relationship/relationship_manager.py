import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

from config import settings
from memory.memory_manager import MemoryStoreError


DB_NAME = str(settings.PROJECT_ROOT / "aria.db")


class RelationshipManager:
    """Persistent people profiles shared by ARIA's relationship-aware features."""

    @staticmethod
    @contextmanager
    def _connection() -> Iterator[sqlite3.Connection]:
        connection = None
        try:
            connection = sqlite3.connect(DB_NAME, timeout=5.0)
            connection.row_factory = sqlite3.Row
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS relationship_profiles (
                    name TEXT PRIMARY KEY COLLATE NOCASE,
                    nickname TEXT,
                    relationship_type TEXT NOT NULL DEFAULT 'acquaintance',
                    preferences TEXT NOT NULL DEFAULT '[]',
                    shared_interests TEXT NOT NULL DEFAULT '[]',
                    trust_level INTEGER NOT NULL DEFAULT 0,
                    privacy_boundaries TEXT NOT NULL DEFAULT '[]',
                    relationship_context TEXT NOT NULL DEFAULT '',
                    authorized_people TEXT NOT NULL DEFAULT '[]',
                    bond_score INTEGER NOT NULL DEFAULT 0,
                    interaction_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS relationship_edges (
                    person_a TEXT NOT NULL COLLATE NOCASE,
                    person_b TEXT NOT NULL COLLATE NOCASE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (person_a, person_b),
                    CHECK (person_a <> person_b)
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(relationship_profiles)"
                ).fetchall()
            }
            for name in ("bond_score", "interaction_count"):
                if name not in columns:
                    connection.execute(
                        f"ALTER TABLE relationship_profiles ADD COLUMN {name} "
                        "INTEGER NOT NULL DEFAULT 0"
                    )
            yield connection
            connection.commit()
        except sqlite3.Error as error:
            if connection is not None:
                connection.rollback()
            raise MemoryStoreError("The relationship database operation failed.") from error
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def save_person(
        name: str,
        *,
        nickname: Optional[str] = None,
        relationship_type: Optional[str] = None,
        preferences=None,
        shared_interests=None,
        trust_level: Optional[int] = None,
        privacy_boundaries=None,
        relationship_context: Optional[str] = None,
        authorized_people=None,
    ) -> Dict[str, Any]:
        name = str(name or "").strip()[:160]
        if not name:
            raise ValueError("A person's name cannot be empty.")
        values = {
            "nickname": nickname,
            "relationship_type": relationship_type,
            "preferences": preferences,
            "shared_interests": shared_interests,
            "trust_level": trust_level,
            "privacy_boundaries": privacy_boundaries,
            "relationship_context": relationship_context,
            "authorized_people": authorized_people,
        }
        with RelationshipManager._connection() as connection:
            existing = connection.execute(
                "SELECT * FROM relationship_profiles WHERE name = ?", (name,)
            ).fetchone()
            profile = dict(existing) if existing else {
                "name": name,
                "nickname": None,
                "relationship_type": "acquaintance",
                "preferences": "[]",
                "shared_interests": "[]",
                "trust_level": 0,
                "privacy_boundaries": "[]",
                "relationship_context": "",
                "authorized_people": "[]",
                "bond_score": 0,
                "interaction_count": 0,
            }
            for key, value in values.items():
                if value is not None:
                    if key == "trust_level":
                        profile[key] = max(0, min(int(value), 100))
                    elif key in {
                        "preferences",
                        "shared_interests",
                        "privacy_boundaries",
                        "authorized_people",
                    }:
                        items = [value] if isinstance(value, str) else value
                        profile[key] = json.dumps(
                            list(
                                dict.fromkeys(
                                    str(item).strip()
                                    for item in items
                                    if str(item).strip()
                                )
                            )
                        )
                    else:
                        profile[key] = str(value).strip()
            connection.execute(
                """
                INSERT INTO relationship_profiles (
                    name, nickname, relationship_type, preferences, shared_interests,
                    trust_level, privacy_boundaries, relationship_context, authorized_people,
                    bond_score, interaction_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    nickname = excluded.nickname,
                    relationship_type = excluded.relationship_type,
                    preferences = excluded.preferences,
                    shared_interests = excluded.shared_interests,
                    trust_level = excluded.trust_level,
                    privacy_boundaries = excluded.privacy_boundaries,
                    relationship_context = excluded.relationship_context,
                    authorized_people = excluded.authorized_people,
                    bond_score = excluded.bond_score,
                    interaction_count = excluded.interaction_count,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    name,
                    profile["nickname"],
                    profile["relationship_type"],
                    profile["preferences"],
                    profile["shared_interests"],
                    profile["trust_level"],
                    profile["privacy_boundaries"],
                    profile["relationship_context"],
                    profile["authorized_people"],
                    profile["bond_score"],
                    profile["interaction_count"],
                ),
            )
        return RelationshipManager.get_person(name)

    @staticmethod
    def get_person(name: str) -> Optional[Dict[str, Any]]:
        with RelationshipManager._connection() as connection:
            row = connection.execute(
                "SELECT * FROM relationship_profiles WHERE name = ?", (str(name).strip(),)
            ).fetchone()
        if not row:
            return None
        record = dict(row)
        for field in (
            "preferences",
            "shared_interests",
            "privacy_boundaries",
            "authorized_people",
        ):
            try:
                value = json.loads(record[field] or "[]")
            except (TypeError, json.JSONDecodeError):
                value = []
            record[field] = value if isinstance(value, list) else []
        return record

    @staticmethod
    def set_relationship(
        name: str, relationship: str, trust_level: int = 50
    ) -> None:
        RelationshipManager.save_person(
            name,
            relationship_type=relationship,
            trust_level=trust_level,
        )

    @staticmethod
    def get_social_context(name: str) -> Dict[str, Any]:
        profile = RelationshipManager.get_person(name)
        if not profile:
            return {"relationship": "unknown", "trust": 0}
        return {
            "relationship": profile["relationship_type"],
            "trust": profile["trust_level"],
            "preferences": profile["preferences"],
            "shared_interests": profile["shared_interests"],
            "privacy_boundaries": profile["privacy_boundaries"],
            "relationship_context": profile["relationship_context"],
            "bond_score": profile["bond_score"],
            "interaction_count": profile["interaction_count"],
        }

    @staticmethod
    def record_interaction(name: str) -> Dict[str, Any]:
        name = str(name or "").strip()
        if not name:
            raise ValueError("A person's name cannot be empty.")
        RelationshipManager.save_person(name)
        with RelationshipManager._connection() as connection:
            connection.execute(
                """
                UPDATE relationship_profiles
                SET bond_score = MIN(100, bond_score + 1),
                    interaction_count = interaction_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE name = ?
                """,
                (name,),
            )
        return RelationshipManager.get_person(name)

    @staticmethod
    def find_person_mentioned(text: str) -> Optional[Dict[str, Any]]:
        lowered = str(text or "").casefold()
        with RelationshipManager._connection() as connection:
            rows = connection.execute(
                "SELECT name, nickname FROM relationship_profiles"
            ).fetchall()
        matches = [
            row
            for row in rows
            if any(
                value and len(value.strip()) >= 2 and value.strip().casefold() in lowered
                for value in (row["name"], row["nickname"])
            )
        ]
        if not matches:
            return None
        match = max(
            matches,
            key=lambda row: max(
                len(value.strip())
                for value in (row["name"], row["nickname"])
                if value and value.strip().casefold() in lowered
            ),
        )
        return RelationshipManager.get_person(match["name"])

    @staticmethod
    def connect_people(person_a: str, person_b: str) -> None:
        person_a = str(person_a or "").strip()[:160]
        person_b = str(person_b or "").strip()[:160]
        if not person_a or not person_b or person_a.casefold() == person_b.casefold():
            raise ValueError("A relationship connection requires two distinct names.")
        first, second = sorted((person_a, person_b), key=str.casefold)
        with RelationshipManager._connection() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO relationship_edges (person_a, person_b) VALUES (?, ?)",
                (first, second),
            )

    @staticmethod
    def get_connections(person: str):
        person = str(person or "").strip()
        with RelationshipManager._connection() as connection:
            rows = connection.execute(
                """
                SELECT person_b AS name FROM relationship_edges WHERE person_a = ?
                UNION
                SELECT person_a AS name FROM relationship_edges WHERE person_b = ?
                ORDER BY name COLLATE NOCASE
                """,
                (person, person),
            ).fetchall()
        return [str(row["name"]) for row in rows]
