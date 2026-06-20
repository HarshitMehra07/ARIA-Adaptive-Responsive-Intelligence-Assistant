from memory.goal_advisor import GoalAdvisor


class WeeklyReview:

    @staticmethod
    def review(memories):

        report = GoalAdvisor.advise(memories)

        return f"""
Progress: {report['progress']}%

Completed:
{", ".join(report['completed'])}

Remaining:
{", ".join(report['missing'])}
"""