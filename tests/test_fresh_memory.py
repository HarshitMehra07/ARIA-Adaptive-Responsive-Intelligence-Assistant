from memory.memory_manager import MemoryManager

MemoryManager.save_memory(
    category="career",
    content="My goal is to become an AI Engineer",
    importance=60
)

MemoryManager.save_memory(
    category="project",
    content="ARIA is my personal assistant project",
    importance=30
)

print("Fresh memories added")