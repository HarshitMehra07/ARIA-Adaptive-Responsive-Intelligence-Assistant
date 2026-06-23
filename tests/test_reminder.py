from memory.reminder_engine import ReminderEngine

ReminderEngine.add(
    "Drink Water",
    "30 minutes"
)

print(
    ReminderEngine.get_all()
)