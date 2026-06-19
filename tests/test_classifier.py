from memory.memory_classifier import MemoryClassifier

samples = [
    "I want to become an AI Engineer",
    "I am going to gym today",
    "ARIA is my personal assistant project",
    "Today is a nice day"
]

for text in samples:

    category = MemoryClassifier.classify(text)

    print(f"{text} -> {category}")