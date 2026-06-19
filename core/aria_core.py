from memory.memory_classifier import MemoryClassifier
from memory.importance_engine import ImportanceEngine
from memory.memory_filter import MemoryFilter
from memory.memory_manager import MemoryManager


class ARIACore:

    @staticmethod
    def process_memory(text):

        category = MemoryClassifier.classify(text)

        importance = ImportanceEngine.score(text)

        print(f"Category: {category}")
        print(f"Importance: {importance}")

        if importance >= 20:

            MemoryManager.save_memory(
                category=category,
                content=text,
                importance=importance
            )

            print("Memory Stored")

        else:

            print("Memory Ignored")