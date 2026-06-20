from memory.task_planner import TaskPlanner


class MissionGenerator:

    @staticmethod
    def generate(memories):

        tasks = TaskPlanner.generate_tasks(memories)

        mission = []

        count = 1

        for task in tasks:

            mission.append(
                f"{count}. {task}"
            )

            count += 1

        return mission