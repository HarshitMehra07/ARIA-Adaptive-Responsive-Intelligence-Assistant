class NLUEngine:

    @staticmethod
    def detect_intent(text):

        text = text.lower()

        if "goal" in text:
            return "goal"

        if "progress" in text:
            return "progress"

        if "project" in text:
            return "project"

        if "career" in text:
            return "career"

        if "task" in text:
            return "task"

        if "mission" in text:
            return "mission"

        return "general"