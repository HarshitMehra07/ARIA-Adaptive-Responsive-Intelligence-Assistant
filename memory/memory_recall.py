from memory.memory_manager import MemoryManager


class MemoryRecall:

    @staticmethod
    def recall(query):

        memories = MemoryManager.get_all_memories()

        query = query.lower()

        matches = []

        for memory in memories:

            content = memory[0].lower()

            if query in content:

                matches.append(memory[0])

        return matches