from __future__ import annotations

import re
import json
import sqlite3
from contextlib import contextmanager
from typing import Dict, Iterator, List, Optional, Tuple

from config import settings


DB_NAME = str(settings.PROJECT_ROOT / "aria.db")


class MemoryStoreError(Exception):
    """Raised when a persistent memory operation cannot be completed."""


class UnsafeMemoryError(MemoryStoreError):
    """Raised when content appears to contain credentials or secrets."""


class MemoryCapacityError(MemoryStoreError):
    """Raised when one owner's bounded long-term memory store is full."""


_SECRET_PATTERNS = (
    re.compile(
        r"\b(?:password|passwd|api[_ -]?key|access[_ -]?token|secret|private[_ -]?key)\b"
        r"\s*(?:[:=]|\bis\b)\s*\S+",
        re.IGNORECASE,
    ),
    re.compile(r"\bBearer\s+\S+", re.IGNORECASE),
    re.compile(r"\b(?:sk-or-v1-|sk-proj-|sk-)[A-Za-z0-9_-]{12,}", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
_PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.IGNORECASE | re.DOTALL,
)
_MEMORY_STOPWORDS = {
    "about", "after", "again", "could", "explain", "from", "have", "help",
    "into", "just", "like", "more", "please", "should", "that", "their",
    "them", "there", "these", "they", "this", "what", "when", "where",
    "which", "with", "would", "your", "forget", "memory", "memories",
    "saved", "remember", "preference", "preferences", "the", "my", "for",
    "i", "is", "are", "was", "were", "do", "does", "did", "can", "am",
    "and", "a", "an", "of", "to", "it", "me", "we", "you",
}
_PRIVACY_LEVELS = {"PRIVATE", "PERSONAL", "SHARED", "PUBLIC"}
_PRIVACY_RESTRICTIVENESS = {
    "PUBLIC": 0,
    "SHARED": 1,
    "PERSONAL": 2,
    "PRIVATE": 3,
}
_PRIMARY_USER_ID = "primary_user"


def contains_secret(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in _SECRET_PATTERNS)


def redact_secrets(text: str) -> str:
    redacted = str(text or "")
    redacted = _PRIVATE_KEY_BLOCK.sub("[redacted secret]", redacted)
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[redacted secret]", redacted)
    return redacted


class MemoryManager:
    """Persistent, privacy-aware SQLite memory using the existing memories table."""

    MAX_MEMORIES_PER_OWNER = 500

    @staticmethod
    @contextmanager
    def _connection() -> Iterator[sqlite3.Connection]:
        connection = None
        try:
            connection = sqlite3.connect(DB_NAME, timeout=5.0)
            connection.row_factory = sqlite3.Row
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT,
                    content TEXT,
                    importance INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(memories)").fetchall()
            }
            migrations = {
                "privacy_level": "TEXT NOT NULL DEFAULT 'PERSONAL'",
                "owner_id": "TEXT NOT NULL DEFAULT 'primary_user'",
                "subject_person": "TEXT",
                "authorized_people": "TEXT NOT NULL DEFAULT '[]'",
                "confidence": "REAL NOT NULL DEFAULT 1.0",
                "occurrence_count": "INTEGER NOT NULL DEFAULT 1",
                "last_accessed": "TIMESTAMP",
                "updated_at": "TIMESTAMP",
            }
            for name, definition in migrations.items():
                if name not in columns:
                    connection.execute(
                        f"ALTER TABLE memories ADD COLUMN {name} {definition}"
                    )
            yield connection
            connection.commit()
        except sqlite3.Error as error:
            if connection is not None:
                connection.rollback()
            raise MemoryStoreError("The memory database operation failed.") from error
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def save_memory(
        category,
        content,
        importance=0,
        *,
        privacy_level="PERSONAL",
        owner_id=_PRIMARY_USER_ID,
        subject_person=None,
        authorized_people=(),
        confidence=1.0,
    ) -> int:
        category = str(category or "general").strip()[:80] or "general"
        content = str(content or "").strip()
        if not content:
            raise MemoryStoreError("Memory content cannot be empty.")
        if contains_secret(content):
            raise UnsafeMemoryError("This content appears to contain a credential or secret.")
        importance = max(0, min(int(importance), 100))
        privacy_level = str(privacy_level or "PERSONAL").strip().upper()
        if privacy_level not in _PRIVACY_LEVELS:
            raise ValueError(f"privacy_level must be one of {sorted(_PRIVACY_LEVELS)}.")
        owner_id = str(owner_id or _PRIMARY_USER_ID).strip()
        if not owner_id:
            raise ValueError("owner_id cannot be empty.")
        subject_person = str(subject_person).strip()[:160] if subject_person else None
        if isinstance(authorized_people, str):
            authorized_people = [authorized_people]
        authorized_people = sorted(
            {
                str(person).strip()
                for person in (authorized_people or ())
                if str(person).strip()
            }
        )
        if privacy_level != "SHARED":
            authorized_people = []
        confidence = max(0.0, min(float(confidence), 1.0))

        with MemoryManager._connection() as connection:
            existing = connection.execute(
                """
                SELECT id, privacy_level, authorized_people, occurrence_count, confidence,
                    importance
                FROM memories
                WHERE lower(category) = lower(?) AND lower(content) = lower(?)
                    AND owner_id = ? AND COALESCE(lower(subject_person), '') = lower(?)
                LIMIT 1
                """,
                (category, content, owner_id, subject_person or ""),
            ).fetchone()
            if existing:
                existing_importance = int(existing["importance"] or 0)
                reinforced_importance = max(existing_importance, importance)
                if importance <= existing_importance:
                    reinforced_importance = min(
                        100,
                        reinforced_importance
                        + min(int(existing["occurrence_count"] or 1) * 5, 15),
                    )
                existing_privacy = str(existing["privacy_level"] or "PERSONAL").upper()
                if existing_privacy not in _PRIVACY_LEVELS:
                    existing_privacy = "PERSONAL"
                if _PRIVACY_RESTRICTIVENESS[existing_privacy] > _PRIVACY_RESTRICTIVENESS[privacy_level]:
                    privacy_level = existing_privacy
                try:
                    existing_authorized = json.loads(existing["authorized_people"] or "[]")
                except (TypeError, json.JSONDecodeError):
                    existing_authorized = []
                merged_authorized = sorted(
                    set(existing_authorized if isinstance(existing_authorized, list) else ())
                    | set(authorized_people)
                )
                if privacy_level != "SHARED":
                    merged_authorized = []
                connection.execute(
                    """
                    UPDATE memories
                    SET importance = ?,
                        privacy_level = ?,
                        authorized_people = ?,
                        occurrence_count = COALESCE(occurrence_count, 1) + 1,
                        confidence = MAX(COALESCE(confidence, 0), ?),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        reinforced_importance,
                        privacy_level,
                        json.dumps(merged_authorized),
                        confidence,
                        int(existing["id"]),
                    ),
                )
                return int(existing["id"])

            count = connection.execute(
                "SELECT COUNT(*) FROM memories WHERE owner_id = ?", (owner_id,)
            ).fetchone()[0]
            if count >= MemoryManager.MAX_MEMORIES_PER_OWNER:
                raise MemoryCapacityError(
                    "Long-term memory is full. Review and forget older memories before saving more."
                )

            cursor = connection.execute(
                """
                INSERT INTO memories (
                    category, content, importance, privacy_level, owner_id,
                    subject_person, authorized_people, confidence, occurrence_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    category,
                    content,
                    importance,
                    privacy_level,
                    owner_id,
                    subject_person,
                    json.dumps(authorized_people),
                    confidence,
                ),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def update_memory(
        memory_id: int,
        content: str,
        *,
        category: Optional[str] = None,
        importance: Optional[int] = None,
        requester_id: str = _PRIMARY_USER_ID,
        privacy_level: Optional[str] = None,
        subject_person: Optional[str] = None,
        authorized_people=None,
    ) -> bool:
        content = str(content or "").strip()
        if not content:
            raise MemoryStoreError("Memory content cannot be empty.")
        if contains_secret(content):
            raise UnsafeMemoryError("This content appears to contain a credential or secret.")
        requester_id = str(requester_id or _PRIMARY_USER_ID)
        if privacy_level is not None:
            privacy_level = str(privacy_level).strip().upper()
            if privacy_level not in _PRIVACY_LEVELS:
                raise ValueError(f"privacy_level must be one of {sorted(_PRIVACY_LEVELS)}.")

        with MemoryManager._connection() as connection:
            existing = connection.execute(
                "SELECT id, owner_id FROM memories WHERE id = ?", (int(memory_id),)
            ).fetchone()
            if not existing or str(existing["owner_id"] or _PRIMARY_USER_ID) != requester_id:
                return False
            fields = ["content = ?"]
            params = [content]
            if category is not None:
                fields.append("category = ?")
                params.append(str(category).strip()[:80] or "general")
            if importance is not None:
                fields.append("importance = ?")
                params.append(max(0, min(int(importance), 100)))
            if privacy_level is not None:
                fields.append("privacy_level = ?")
                params.append(privacy_level)
            if subject_person is not None:
                fields.append("subject_person = ?")
                params.append(str(subject_person).strip()[:160] or None)
            if privacy_level is not None and privacy_level != "SHARED":
                fields.append("authorized_people = '[]'")
            elif authorized_people is not None:
                if isinstance(authorized_people, str):
                    authorized_people = [authorized_people]
                authorized = sorted(
                    {
                        str(person).strip()
                        for person in authorized_people
                        if str(person).strip()
                    }
                )
                fields.append("authorized_people = ?")
                params.append(json.dumps(authorized))
            fields.append("updated_at = CURRENT_TIMESTAMP")
            params.append(int(memory_id))
            connection.execute(
                f"UPDATE memories SET {', '.join(fields)} WHERE id = ?", tuple(params)
            )
            return True

    @staticmethod
    def get_memory(
        memory_id: int, requester_id: str = _PRIMARY_USER_ID
    ) -> Optional[Dict[str, object]]:
        with MemoryManager._connection() as connection:
            row = connection.execute(
                "SELECT * FROM memories WHERE id = ?",
                (int(memory_id),),
            ).fetchone()
            if not row or not MemoryManager._can_access(row, requester_id):
                return None
            record = dict(row)
            connection.execute(
                "UPDATE memories SET last_accessed = CURRENT_TIMESTAMP WHERE id = ?",
                (int(memory_id),),
            )
            if contains_secret(str(record.get("content") or "")):
                record["content"] = "[redacted possible secret]"
                record["redacted"] = True
            return record

    @staticmethod
    def list_memories(
        limit: int = 100,
        requester_id: str = _PRIMARY_USER_ID,
        subject_person: Optional[str] = None,
    ) -> List[Dict[str, object]]:
        limit = max(1, min(int(limit), 500))
        with MemoryManager._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM memories ORDER BY id DESC"
            ).fetchall()
            records = []
            for row in rows:
                if not MemoryManager._can_access(row, requester_id):
                    continue
                if subject_person and str(row["subject_person"] or "").casefold() != str(
                    subject_person
                ).casefold():
                    continue
                record = dict(row)
                if contains_secret(str(record.get("content") or "")):
                    record["content"] = "[redacted possible secret]"
                    record["redacted"] = True
                records.append(record)
            return records[:limit]

    @staticmethod
    def find_memories(
        query: str,
        limit: int = 5,
        *,
        requester_id: str = _PRIMARY_USER_ID,
        subject_person: Optional[str] = None,
        current_goal: Optional[str] = None,
        recent_context=(),
    ) -> List[Dict[str, object]]:
        tokens = list(dict.fromkeys(re.findall(r"[\w'-]{2,}", (query or "").lower())))
        tokens = [token for token in tokens if token not in _MEMORY_STOPWORDS][:8]
        context_tokens = []
        for context in (current_goal, subject_person, *(recent_context or ())):
            context_tokens.extend(
                token
                for token in re.findall(r"[\w'-]{2,}", str(context or "").lower())
                if token not in _MEMORY_STOPWORDS
            )
        context_tokens = list(dict.fromkeys(context_tokens))[:8]
        all_tokens = list(dict.fromkeys(tokens + context_tokens))
        if not all_tokens:
            return []
        limit = max(1, min(int(limit), 50))
        predicates = " OR ".join(
            "instr(lower(content), lower(?)) > 0 OR instr(lower(COALESCE(subject_person, '')), lower(?)) > 0"
            for _ in all_tokens
        )
        token_params = tuple(value for token in all_tokens for value in (token, token))
        with MemoryManager._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM memories WHERE "
                + predicates
                + " ORDER BY COALESCE(importance, 0) DESC, id DESC",
                token_params,
            ).fetchall()
        scored = []
        for row in rows:
            if not MemoryManager._can_access(row, requester_id):
                continue
            record = dict(row)
            if contains_secret(str(record.get("content") or "")):
                continue
            lowered = str(record.get("content") or "").lower()
            subject = str(record.get("subject_person") or "").lower()
            score = sum(token in lowered for token in tokens)
            score += sum(token in lowered or token in subject for token in context_tokens)
            if subject_person and subject == subject_person.strip().lower():
                score += 3
            scored.append((score, int(record.get("importance") or 0), record))
        scored.sort(key=lambda item: (item[0], item[1], item[2]["id"]), reverse=True)
        selected = [item[2] for item in scored[:limit]]
        if selected:
            with MemoryManager._connection() as connection:
                connection.executemany(
                    "UPDATE memories SET last_accessed = CURRENT_TIMESTAMP WHERE id = ?",
                    [(int(record["id"]),) for record in selected],
                )
        return selected

    @staticmethod
    def get_memories_by_category(
        category, requester_id: str = _PRIMARY_USER_ID
    ) -> List[Tuple[str]]:
        with MemoryManager._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM memories WHERE lower(category) = lower(?) ORDER BY id DESC",
                (str(category),),
            ).fetchall()
            return [
                ("[redacted possible secret]" if contains_secret(str(row["content"] or "")) else str(row["content"]),)
                for row in rows
                if MemoryManager._can_access(row, requester_id)
            ]

    @staticmethod
    def get_all_memories(
        requester_id: str = _PRIMARY_USER_ID
    ) -> List[Tuple[str]]:
        with MemoryManager._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM memories ORDER BY id DESC"
            ).fetchall()
            return [
                ("[redacted possible secret]" if contains_secret(str(row["content"] or "")) else str(row["content"]),)
                for row in rows
                if MemoryManager._can_access(row, requester_id)
            ]

    @staticmethod
    def search_memories(query: str) -> List[Tuple[str]]:
        return [(str(item["content"]),) for item in MemoryManager.find_memories(query)]

    @staticmethod
    def delete_memory(
        memory_id: int, requester_id: str = _PRIMARY_USER_ID
    ) -> bool:
        with MemoryManager._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM memories WHERE id = ? AND owner_id = ?",
                (int(memory_id), str(requester_id or _PRIMARY_USER_ID)),
            )
            return cursor.rowcount > 0

    @staticmethod
    def forget_memories(
        query: str, requester_id: str = _PRIMARY_USER_ID
    ) -> int:
        query = (query or "").strip().lower()
        if not query:
            return 0
        tokens = list(dict.fromkeys(re.findall(r"[\w'-]{2,}", query)))
        tokens = [token for token in tokens if token not in _MEMORY_STOPWORDS][:8]
        if not tokens:
            return 0
        predicates = " AND ".join("instr(lower(content), lower(?)) > 0" for _ in tokens)
        with MemoryManager._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM memories WHERE owner_id = ? AND " + predicates,
                (str(requester_id or _PRIMARY_USER_ID), *tokens),
            )
            return cursor.rowcount

    @staticmethod
    def delete_all_memories(
        requester_id: str = _PRIMARY_USER_ID
    ) -> int:
        with MemoryManager._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM memories WHERE owner_id = ?",
                (str(requester_id or _PRIMARY_USER_ID),),
            )
            return cursor.rowcount

    @staticmethod
    def _can_access(record, requester_id: str) -> bool:
        requester_id = str(requester_id or _PRIMARY_USER_ID)
        owner_id = str(record["owner_id"] or _PRIMARY_USER_ID)
        privacy = str(record["privacy_level"] or "PERSONAL").upper()
        if owner_id == requester_id:
            return True
        if privacy == "PUBLIC":
            return True
        if privacy != "SHARED":
            return False
        try:
            authorized = json.loads(record["authorized_people"] or "[]")
        except (TypeError, json.JSONDecodeError):
            return False
        return isinstance(authorized, list) and requester_id in authorized
