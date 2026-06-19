from memory.memory_manager import MemoryManager

memories = MemoryManager.get_memories_by_category("career")

print("\nCareer Memories:\n")

for memory in memories:
    print("-", memory[0])