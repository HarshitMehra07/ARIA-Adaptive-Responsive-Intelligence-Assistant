from memory.importance_engine import ImportanceEngine
from memory.memory_classifier import MemoryClassifier
from memory.memory_type_engine import MemoryTypeEngine
from memory.memory_filter import MemoryFilter
from memory.memory_manager import MemoryManager
from memory.profile_builder import ProfileBuilder

class ARIACore:

    @staticmethod
    def process(text):

        print("\n========================")
        print("USER:", text)

        # Category Detection
        category = MemoryClassifier.classify(text)

        # Importance Score
        importance = ImportanceEngine.score(text)

        # Memory Type
        memory_type = MemoryTypeEngine.determine_type(text)

        print("Category:", category)
        print("Importance:", importance)
        print("Memory Type:", memory_type)

        # Store Decision
        if MemoryFilter.should_store(text):

            MemoryManager.save_memory(
                category=category,
                content=text,
                importance=importance
            )

            print("Status: Memory Stored")

        else:

            print("Status: Memory Ignored")

        print("========================")
        
        ProfileBuilder.update_profile(text)