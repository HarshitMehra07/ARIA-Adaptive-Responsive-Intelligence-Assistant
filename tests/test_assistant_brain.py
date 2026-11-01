from assistant.assistant_brain import (
    AssistantBrain
)

print(
    "\n===== ASSISTANT BRAIN =====\n"
)

result = AssistantBrain.think(

    "stressed",

    "coding"

)

for key, value in result.items():

    print(
        key,
        ":",
        value
    )