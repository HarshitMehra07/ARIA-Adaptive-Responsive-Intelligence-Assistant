from memory.memory_manager import MemoryManager

print("\n===== ARIA DATABASE TEST =====\n")

memories = MemoryManager.get_all_memories()

print("Total Memories Found:", len(memories))

print("\nStored Memories:\n")

for memory in memories:
    print("-", memory[0])

print("\n===== TEST COMPLETE =====")