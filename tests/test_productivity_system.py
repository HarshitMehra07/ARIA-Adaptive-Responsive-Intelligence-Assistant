from memory.mission_generator import MissionGenerator
from memory.daily_planner import DailyPlanner
from memory.weekly_review import WeeklyReview
from memory.recommendation_engine import RecommendationEngine
from memory.daily_report import DailyReport

memories = [

    "I completed Python",

    "I learned DSA",

    "I built projects",

    "I go gym every day",

    "I study coding daily"
]

print("\n===== MISSION =====")

print(
    MissionGenerator.generate(memories)
)

print("\n===== PLANNER =====")

print(
    DailyPlanner.build(memories)
)

print("\n===== WEEKLY REVIEW =====")

print(
    WeeklyReview.review(memories)
)

print("\n===== RECOMMENDATIONS =====")

print(
    RecommendationEngine.recommend(memories)
)

print("\n===== DAILY REPORT =====")

print(
    DailyReport.generate(memories)
)