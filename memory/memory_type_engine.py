from memory.importance_engine import ImportanceEngine
from memory.memory_types import MemoryTypes

class MemoryTypeEngine:

    @staticmethod
    def determine_type(text):

        score = ImportanceEngine.score(text)

        if score >= 60:
            return MemoryTypes.CORE_IDENTITY

        if score >= 15:
            return MemoryTypes.LONG_TERM

        return MemoryTypes.TEMPORARY