from memory.task_planner import TaskPlanner

memories = [

    "I completed Python",

    "I learned DSA",

    "I built projects"

]

tasks = TaskPlanner.generate_tasks(
    memories
)

print("\n===== DAILY TASKS =====\n")

for task in tasks:

    print("-", task)