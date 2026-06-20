from memory.goal_advisor import GoalAdvisor


class TaskPlanner:

    @staticmethod
    def generate_tasks(memories):

        report = GoalAdvisor.advise(memories)

        tasks = []

        for skill in report["missing"]:

            if skill == "machine learning":

                tasks.append(
                    "Learn ML fundamentals for 1 hour"
                )

            elif skill == "deep learning":

                tasks.append(
                    "Study Neural Networks for 1 hour"
                )

            elif skill == "internship":

                tasks.append(
                    "Search and apply for internships"
                )

        return tasks