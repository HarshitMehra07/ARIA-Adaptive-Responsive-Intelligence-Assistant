from memory.memory_manager import MemoryManager


class LearningEngine:

    @staticmethod
    def learn(text):

        lower = text.lower()

        if (
            "i like" in lower
            or "i love" in lower
            or "my favorite" in lower
        ):

            MemoryManager.save_memory(
                "preference",
                text,
                40
            )

            return True

        return False