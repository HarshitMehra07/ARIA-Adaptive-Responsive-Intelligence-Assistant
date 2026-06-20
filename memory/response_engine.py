class ResponseEngine:

    @staticmethod
    def generate(intent):

        responses = {

            "goal":
            "Let me analyze your goals.",

            "progress":
            "Let me calculate your progress.",

            "project":
            "Let me check your projects.",

            "career":
            "Let me review your career plan.",

            "task":
            "Let me create tasks for you.",

            "mission":
            "Let me generate today's mission.",

            "general":
            "Tell me more."
        }

        return responses.get(
            intent,
            "I don't understand."
        )