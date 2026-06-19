from core.aria_core import ARIACore

samples = [
    "My goal is to become an AI Engineer",
    "I am going to gym regularly",
    "ARIA is my personal assistant project",
    "Hello",
    "I ate paneer today"
]

for text in samples:

    print("\n------------------")

    ARIACore.process_memory(text)