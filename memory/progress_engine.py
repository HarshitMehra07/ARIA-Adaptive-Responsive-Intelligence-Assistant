from memory.skill_tracker import SkillTracker


class ProgressEngine:

    @staticmethod
    def calculate(memories):

        completed = SkillTracker.check_progress(memories)

        total = len(SkillTracker.AI_ENGINEER_SKILLS)

        done = len(completed)

        percentage = int((done / total) * 100)

        return {

            "completed": completed,

            "percentage": percentage

        }