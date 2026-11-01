from core.awareness_engine import (
    AwarenessEngine
)

print(
    "\n===== AWARENESS =====\n"
)

result = AwarenessEngine.observe()

for key, value in result.items():

    print(
        key,
        ":",
        value
    )