from memory.importance_engine import ImportanceEngine

samples = [
    "My goal is to become an AI Engineer",
    "I am learning Python",
    "I ate paneer today",
    "Hello"
]

for text in samples:

    score = ImportanceEngine.score(text)

    print(f"{text} -> {score}")