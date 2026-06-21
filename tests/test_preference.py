from memory.preference_engine import PreferenceEngine

PreferenceEngine.learn(
    "I like Python"
)

PreferenceEngine.learn(
    "I like Gym"
)

PreferenceEngine.learn(
    "I dislike Procrastination"
)

print(
    PreferenceEngine.get_preferences()
)