class DecisionEngine:

    @staticmethod
    def decide(intent):

        decisions = {

            "goal":
            "goal_system",

            "progress":
            "progress_system",

            "mission":
            "mission_system",

            "career":
            "reasoning_system",

            "chat":
            "conversation_system"

        }

        return decisions.get(
            intent,
            "conversation_system"
        )