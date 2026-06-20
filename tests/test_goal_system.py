from memory.goal_tracker import GoalTracker
from memory.goal_advisor import GoalAdvisor

GoalTracker.add_goal(
    "AI Engineer"
)

memories = [

    "I completed Python",

    "I learned DSA",

    "I built projects"

]

result = GoalAdvisor.advise(
    memories
)

print("\n===== GOAL REPORT =====")

print(
    "Progress:",
    result["progress"],
    "%"
)

print(
    "Completed:",
    result["completed"]
)

print(
    "Missing:",
    result["missing"]
)