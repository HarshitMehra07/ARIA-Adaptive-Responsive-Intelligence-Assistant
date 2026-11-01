from memory.memory_manager import MemoryManager


class MemoryRecall:

    @staticmethod
    def recall(
        query,
        limit=5,
        *,
        requester_id="primary_user",
        subject_person=None,
        current_goal=None,
        recent_context=(),
    ):
        """Return a relevant, access-controlled subset of durable memories."""
        matches = MemoryManager.find_memories(
            query,
            limit=limit,
            requester_id=requester_id,
            subject_person=subject_person,
            current_goal=current_goal,
            recent_context=recent_context,
        )
        return [str(memory["content"]) for memory in matches]
