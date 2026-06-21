class IntentEngine:

    @staticmethod
    def detect(text):

        lower = text.lower()

        if "goal" in lower:
            return "goal"

        if "progress" in lower:
            return "progress"

        if "mission" in lower:
            return "mission"

        if "plan" in lower:
            return "planning"

        if "career" in lower:
            return "career"

        if "how" in lower:
            return "question"

        return "chat"