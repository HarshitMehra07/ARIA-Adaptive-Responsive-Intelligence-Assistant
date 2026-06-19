from memory.memory_filter import MemoryFilter

text = "My goal is to become an AI Engineer"

score = MemoryFilter.calculate_importance(text)

print("Score:", score)

print("Store:", MemoryFilter.should_store(text))