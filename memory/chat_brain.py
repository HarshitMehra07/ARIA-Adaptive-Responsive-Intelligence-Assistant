from memory.conversation_memory import ConversationMemory
from memory.context_engine import ContextEngine
from memory.reasoning_engine import ReasoningEngine
from memory.conversation_engine import ConversationEngine


class ChatBrain:

    @staticmethod
    def chat(text):

        ConversationMemory.add(text)

        resolved = ContextEngine.resolve(text)

        lower = resolved.lower()

        # Goal / Career Handling
        if (
            "goal" in lower
            or "career" in lower
            or "engineer" in lower
            or "achieve" in text.lower()
        ):

            return (
                "Your goal is AI Engineer. "
                "Focus on Python, DSA, Machine Learning, "
                "Deep Learning, Projects, and Internships."
            )

        # Progress
        elif "progress" in lower:

            return (
                "I can analyze your goal progress."
            )

        # Mission
        elif "mission" in lower:

            return (
                "I can generate today's mission."
            )

        return ConversationEngine.reply(resolved)