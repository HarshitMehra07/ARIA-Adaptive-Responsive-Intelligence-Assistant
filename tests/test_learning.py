from memory.learning_engine import LearningEngine

print("\n===== LEARNING TEST =====\n")

LearningEngine.learn_fact(
    "title",
    "Boss"
)

LearningEngine.learn_fact(
    "theme",
    "Dark"
)

print(
    LearningEngine.get(
        "title"
    )
)

print(
    LearningEngine.get_all()
)