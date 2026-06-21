from memory.emotion_engine import EmotionEngine

print("Emotion Tests")

print(
    EmotionEngine.detect(
        "I am very happy today"
    )
)

print(
    EmotionEngine.detect(
        "I am stressed about exams"
    )
)

print(
    EmotionEngine.detect(
        "I am angry right now"
    )
)

print(
    EmotionEngine.detect(
        "Today is normal"
    )
)