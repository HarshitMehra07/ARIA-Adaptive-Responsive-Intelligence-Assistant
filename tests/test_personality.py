from memory.personality_engine import PersonalityEngine

print(
    PersonalityEngine.get_mode()
)

PersonalityEngine.set_mode(
    "mentor"
)

print(
    PersonalityEngine.get_mode()
)

PersonalityEngine.set_mode(
    "coach"
)

print(
    PersonalityEngine.get_mode()
)