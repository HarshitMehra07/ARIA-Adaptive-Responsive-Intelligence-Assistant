from memory.scheduler_engine import SchedulerEngine

print(
    SchedulerEngine.parse(
        "Remind me in 30 minutes"
    )
)

print(
    SchedulerEngine.parse(
        "Remind me in 2 hours"
    )
)