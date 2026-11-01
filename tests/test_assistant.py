from assistant.mood_engine import MoodEngine
from assistant.care_engine import CareEngine
from assistant.empathy_engine import EmpathyEngine
from assistant.intervention_engine import (
    InterventionEngine
)

print(
    "\n===== ASSISTANT =====\n"
)

print(
    MoodEngine.detect(
        "stressed"
    )
)

print(
    CareEngine.care(
        "coding"
    )
)

print(
    EmpathyEngine.reply(
        "sad"
    )
)

print(
    InterventionEngine.intervene(
        "phone"
    )
)