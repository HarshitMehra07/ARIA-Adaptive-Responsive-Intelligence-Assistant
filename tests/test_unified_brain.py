from memory.unified_brain import UnifiedBrain

result = UnifiedBrain.process(

    "My goal is to become an AI Engineer"

)

print("\n===== UNIFIED BRAIN =====\n")

for key, value in result.items():

    print(
        f"{key}: {value}"
    )