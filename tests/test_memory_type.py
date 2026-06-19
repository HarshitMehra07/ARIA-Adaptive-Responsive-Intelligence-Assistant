from memory.memory_type_engine import MemoryTypeEngine

samples = [
    "My goal is to become an AI Engineer",
    "I am going gym today",
    "Hello there"
]

for text in samples:

    memory_type = MemoryTypeEngine.determine_type(text)

    print("\nText:", text)
    print("Type:", memory_type)