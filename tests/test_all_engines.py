from memory.emotion_engine import EmotionEngine
from memory.intent_engine import IntentEngine
from memory.entity_extractor import EntityExtractor
from memory.preference_engine import PreferenceEngine
from memory.personality_engine import PersonalityEngine

print("\n===== EMOTION =====")
print(
    EmotionEngine.detect(
        "I am excited and happy"
    )
)

print("\n===== INTENT =====")
print(
    IntentEngine.detect(
        "Show my progress"
    )
)

print("\n===== ENTITIES =====")
print(
    EntityExtractor.extract(
        "I study Python and Machine Learning"
    )
)

print("\n===== PREFERENCES =====")

PreferenceEngine.learn(
    "I like AI"
)

print(
    PreferenceEngine.get_preferences()
)

print("\n===== PERSONALITY =====")

print(
    PersonalityEngine.get_mode()
)

PersonalityEngine.set_mode(
    "mentor"
)

print(
    PersonalityEngine.get_mode()
)