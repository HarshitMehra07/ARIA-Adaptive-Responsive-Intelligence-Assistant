from memory.aria_brain import ARIABrain

result = ARIABrain.process(
    "My goal is to become an AI Engineer"
)

print("\n===== ARIA BRAIN =====\n")

for key, value in result.items():

    print(
        f"{key}: {value}"
    )