from memory.memory_manager import MemoryManager


class MemoryQuestionEngine:

    @staticmethod
    def answer(question):

        question = question.lower()

        memories = MemoryManager.get_all_memories()

        memory_texts = []

        for memory in memories:

            if isinstance(memory, tuple):
                memory_texts.append(memory[0])
            else:
                memory_texts.append(memory)

        # Goal Questions
        if "goal" in question:

            for memory in memory_texts:

                if "goal" in memory.lower():
                    return memory

            return "I don't know your goals yet."

        # Project Questions
        if "project" in question:

            for memory in memory_texts:

                if "project" in memory.lower():
                    return memory

            return "I don't know your projects yet."

        # Engineer Questions
        if "engineer" in question:

            for memory in memory_texts:

                if "engineer" in memory.lower():
                    return memory

            return "No engineer related memory found."

        return "I don't know the answer yet."