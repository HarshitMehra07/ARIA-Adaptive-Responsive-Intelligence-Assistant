from memory.memory_recall import MemoryRecall

results = MemoryRecall.recall("engineer")

print("\nRecall Results:\n")

for result in results:

    print("-", result)