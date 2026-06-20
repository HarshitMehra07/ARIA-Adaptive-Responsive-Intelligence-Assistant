from memory.conversation_memory import ConversationMemory
from memory.context_engine import ContextEngine
from memory.reasoning_engine import ReasoningEngine
from memory.conversation_engine import ConversationEngine


class ChatBrain:

    @staticmethod
    def chat(text):

        ConversationMemory.add(text)

        resolved = ContextEngine.resolve(
            text
        )

        lower = resolved.lower()

        if "career" in lower:

            return ReasoningEngine.answer(
                resolved
            )

        if "goal" in lower:

            return ReasoningEngine.answer(
                resolved
            )

        return ConversationEngine.reply(
            resolved
        )