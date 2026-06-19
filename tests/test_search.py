from memory.memory_manager import MemoryManager

results = MemoryManager.search_memories("AI")

print("\nSearch Results:\n")

for result in results:
    print("-", result[0])