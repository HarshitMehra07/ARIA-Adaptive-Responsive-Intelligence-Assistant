import sys
import os
import sqlite3
import tempfile

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database.schema as schema
import memory.memory_manager as memory_manager_module
from core.aria_core import AriaCore
from core.cloud_model_client import CloudModelResponse
from core.conversation_manager import ConversationManager
from memory.memory_manager import MemoryManager


def _avoid_live_database():
    current = os.path.abspath(memory_manager_module.DB_NAME)
    live = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "aria.db"))
    if current != live:
        return
    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    handle.close()
    memory_manager_module.DB_NAME = handle.name
    schema.DB_NAME = handle.name
    conn = sqlite3.connect(handle.name)
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
    conn.commit()
    conn.close()


class FakeCloudClient:
    def complete(self, messages, **kwargs):
        return CloudModelResponse(
            text=f"Cloud reply: {messages[-1]['content']}",
            model="mock-model",
            raw={},
        )


def test_goal_setting_and_recall():
    print("\n--- Running Brain Loop Test ---")
    _avoid_live_database()
    aria = AriaCore(cloud_client=FakeCloudClient())

    ConversationManager.clear()
    MemoryManager.delete_all_memories()

    print("\nTest 1: Setting a goal...")
    response1 = aria.process_input("My goal is to become an AI Engineer.")
    print(f"ARIA Response: {response1}")
    assert "AI Engineer" in response1

    print("\nTest 2: Context resolution (asking about it)...")
    response2 = aria.process_input("How can I achieve it?")
    print(f"ARIA Response: {response2}")
    assert response1 != response2

    print("\nTest 3: Memory recall...")
    response3 = aria.process_input("What was my goal again?")
    print(f"ARIA Response: {response3}")

    print("\n--- Brain Loop Test Passed! ---")

if __name__ == "__main__":
    try:
        test_goal_setting_and_recall()
    except Exception as e:
        print(f"Test Failed: {e}")
        sys.exit(1)
