class SkillTracker:

    AI_ENGINEER_SKILLS = [
        "python",
        "dsa",
        "machine learning",
        "deep learning",
        "projects",
        "internship"
    ]

    @staticmethod
    def check_progress(memories):

        completed = []

        for memory in memories:

            text = memory.lower()

            for skill in SkillTracker.AI_ENGINEER_SKILLS:

                if skill in text:

                    completed.append(skill)

        return list(set(completed))