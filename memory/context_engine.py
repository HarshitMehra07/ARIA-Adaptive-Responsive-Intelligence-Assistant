from memory.conversation_memory import ConversationMemory


class ContextEngine:

    @staticmethod
    def resolve(question):

        question_lower = question.lower()

        if "it" in question_lower:

            history = ConversationMemory.get_history()

            if len(history) >= 2:

                previous_message = history[-2]

                print(
                    "Resolved Context:",
                    previous_message
                )

                return previous_message

        return question