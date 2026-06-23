from memory.learning_engine import LearningEngine
from memory.reminder_engine import ReminderEngine
from memory.scheduler_engine import SchedulerEngine
from memory.notification_engine import NotificationEngine
from memory.user_rules_engine import UserRulesEngine

print("\n===== PHASE 2 TEST =====\n")

LearningEngine.learn_fact(
    "title",
    "Boss"
)

UserRulesEngine.set_rule(
    "title",
    "Boss"
)

ReminderEngine.add(
    "Drink Water",
    "30 minutes"
)

print(
    ReminderEngine.get_all()
)

print(
    SchedulerEngine.parse(
        "Remind me in 30 minutes"
    )
)

NotificationEngine.notify(
    "Boss, drink water."
)

print(
    LearningEngine.get_all()
)