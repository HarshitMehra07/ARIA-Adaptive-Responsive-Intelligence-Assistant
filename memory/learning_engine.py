from memory.memory_manager import MemoryManager


class LearningEngine:

    knowledge = {}

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

    @staticmethod
    def learn_fact(key, value):

        LearningEngine.knowledge[key] = value

        print(
            "Learned:",
            key
        )

    @staticmethod
    def get(key):

        return LearningEngine.knowledge.get(
            key,
            None
        )

    @staticmethod
    def get_all():

        return LearningEngine.knowledge