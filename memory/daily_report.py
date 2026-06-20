from memory.habit_tracker import HabitTracker
from memory.goal_advisor import GoalAdvisor


class DailyReport:

    @staticmethod
    def generate(memories):

        habits = HabitTracker.detect(memories)

        progress = GoalAdvisor.advise(memories)

        return {

            "habits": habits,

            "progress": progress["progress"]

        }