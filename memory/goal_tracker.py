import sqlite3

DB_NAME = "aria.db"


class GoalTracker:

    @staticmethod
    def add_goal(goal):

        conn = sqlite3.connect(DB_NAME)

        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO goals
            (goal_name, status)
            VALUES (?, ?)
            """,
            (goal, "active")
        )

        conn.commit()
        conn.close()

        print("Goal Added")

    @staticmethod
    def get_goals():

        conn = sqlite3.connect(DB_NAME)

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT goal_name
            FROM goals
            """
        )

        results = cursor.fetchall()

        conn.close()

        return results