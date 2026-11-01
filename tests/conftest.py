import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolate_sqlite(tmp_path, monkeypatch):
    """Keep tests off the live aria.db file."""
    # Tests must never spend credits or contact configured external services.
    monkeypatch.setattr("config.settings.TAVILY_API_KEY", "")
    db_path = tmp_path / "aria-test.db"
    monkeypatch.setattr("memory.memory_manager.DB_NAME", str(db_path))
    monkeypatch.setattr("memory.goal_tracker.DB_NAME", str(db_path))
    monkeypatch.setattr("relationship.relationship_manager.DB_NAME", str(db_path))
    monkeypatch.setattr("database.schema.DB_NAME", str(db_path))
    monkeypatch.setattr("database.database.DATABASE_NAME", str(db_path))

    conn = sqlite3.connect(db_path)
    conn.execute(
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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_name TEXT,
            status TEXT,
            deadline TEXT
        )
        """
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture(autouse=True)
def isolate_conversation_state():
    from core.conversation_manager import ConversationManager

    ConversationManager.clear()
