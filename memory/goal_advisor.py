from memory.progress_engine import ProgressEngine
from memory.skill_tracker import SkillTracker


class GoalAdvisor:

    @staticmethod
    def advise(memories):

        progress = ProgressEngine.calculate(memories)

        completed = progress["completed"]

        missing = []

        for skill in SkillTracker.AI_ENGINEER_SKILLS:

            if skill not in completed:

                missing.append(skill)

        return {

            "progress": progress["percentage"],

            "completed": completed,

            "missing": missing
        }