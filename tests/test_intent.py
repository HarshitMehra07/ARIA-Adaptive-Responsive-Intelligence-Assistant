from memory.intent_engine import IntentEngine

print("Intent Tests")

print(
    IntentEngine.detect(
        "Show my goal"
    )
)

print(
    IntentEngine.detect(
        "Show progress"
    )
)

print(
    IntentEngine.detect(
        "Create today's mission"
    )
)

print(
    IntentEngine.detect(
        "How can I become successful?"
    )
)

print(
    IntentEngine.detect(
        "Hello ARIA"
    )
)