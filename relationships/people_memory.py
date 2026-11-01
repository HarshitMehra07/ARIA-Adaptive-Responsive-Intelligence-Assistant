from memory.memory_manager import MemoryManager


class PeopleMemory:
    """Compatibility facade storing person facts in privacy-aware long-term memory."""

    @staticmethod
    def remember(
        name,
        fact,
        *,
        privacy_level="PERSONAL",
        owner_id="primary_user",
        authorized_people=(),
    ):
        return MemoryManager.save_memory(
            "relationship",
            fact,
            importance=30,
            privacy_level=privacy_level,
            owner_id=owner_id,
            subject_person=name,
            authorized_people=authorized_people,
        )

    @staticmethod
    def recall(name, *, requester_id="primary_user"):
        matches = MemoryManager.find_memories(
            str(name),
            limit=50,
            requester_id=requester_id,
            subject_person=str(name),
        )
        return [str(memory["content"]) for memory in matches]
