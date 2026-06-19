import sqlite3

DB_NAME = "aria.db"


class MemoryManager:

    @staticmethod
    def save_memory(category, content, importance):

        conn = sqlite3.connect(DB_NAME)

        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO memories
            (category, content, importance)
            VALUES (?, ?, ?)
            """,
            (category, content, importance)
        )

        conn.commit()
        conn.close()

        print("Memory Saved")

    @staticmethod
    def get_memories_by_category(category):

        conn = sqlite3.connect(DB_NAME)

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT content
            FROM memories
            WHERE category = ?
            """,
            (category,)
        )

        results = cursor.fetchall()

        conn.close()

        return results

    @staticmethod
    def get_all_memories():

        conn = sqlite3.connect(DB_NAME)

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT content
            FROM memories
            """
        )

        results = cursor.fetchall()

        conn.close()

        return results

    @staticmethod
    def delete_all_memories():

        conn = sqlite3.connect(DB_NAME)

        cursor = conn.cursor()

        cursor.execute(
            """
            DELETE FROM memories
            """
        )

        conn.commit()
        conn.close()

        print("All Memories Deleted")