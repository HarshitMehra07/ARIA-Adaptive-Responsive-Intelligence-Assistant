from memory.conversation_engine import ConversationEngine
from memory.reasoning_engine import ReasoningEngine


class ChatBrain:

    @staticmethod
    def chat(text):

        lower = text.lower()

        if "career" in lower:

            return ReasoningEngine.answer(
                text
            )

        return ConversationEngine.reply(
            text
        )