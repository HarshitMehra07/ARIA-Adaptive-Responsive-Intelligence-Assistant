import sqlite3
from contextlib import contextmanager
from typing import Iterator, List, Optional, Tuple

from config import settings
from memory.memory_manager import MemoryStoreError, UnsafeMemoryError, contains_secret


DB_NAME = str(settings.PROJECT_ROOT / "aria.db")


class GoalTracker:
    """Persistent active-goal access using the existing SQLite goals table."""

    @staticmethod
    @contextmanager
    def _connection() -> Iterator[sqlite3.Connection]:
        connection = None
        try:
            connection = sqlite3.connect(DB_NAME, timeout=5.0)
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS goals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal_name TEXT,
                    status TEXT,
                    deadline TEXT
                )
                """
            )
            yield connection
            connection.commit()
        except sqlite3.Error as error:
            if connection is not None:
                connection.rollback()
            raise MemoryStoreError("The goal database operation failed.") from error
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def add_goal(goal: str) -> int:
        return GoalTracker.set_active_goal(goal)

    @staticmethod
    def set_active_goal(goal: str) -> int:
        goal = str(goal or "").strip()
        if not goal:
            raise ValueError("Goal cannot be empty.")
        if contains_secret(goal):
            raise UnsafeMemoryError("This goal appears to contain a credential or secret.")
        with GoalTracker._connection() as connection:
            connection.execute(
                "UPDATE goals SET status = ? WHERE lower(status) = ?",
                ("superseded", "active"),
            )
            cursor = connection.execute(
                "INSERT INTO goals (goal_name, status) VALUES (?, ?)", (goal, "active")
            )
            return int(cursor.lastrowid)

    @staticmethod
    def get_active_goal() -> Optional[str]:
        with GoalTracker._connection() as connection:
            row = connection.execute(
                "SELECT goal_name FROM goals WHERE lower(status) = 'active' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return str(row[0]) if row else None

    @staticmethod
    def get_goals() -> List[Tuple[str]]:
        with GoalTracker._connection() as connection:
            return connection.execute(
                "SELECT goal_name FROM goals ORDER BY id DESC"
            ).fetchall()

    @staticmethod
    def delete_goal(goal_id: int) -> bool:
        with GoalTracker._connection() as connection:
            cursor = connection.execute("DELETE FROM goals WHERE id = ?", (int(goal_id),))
            return cursor.rowcount > 0
