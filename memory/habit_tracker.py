class HabitTracker:

    HABITS = [

        "gym",

        "study",

        "coding",

        "reading"

    ]

    @staticmethod
    def detect(memories):

        found = []

        for memory in memories:

            text = memory.lower()

            for habit in HabitTracker.HABITS:

                if habit in text:

                    found.append(habit)

        return list(set(found))