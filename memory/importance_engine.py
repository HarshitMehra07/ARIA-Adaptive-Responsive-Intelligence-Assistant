class ImportanceEngine:

    HIGH_IMPORTANCE = [
        "goal",
        "dream",
        "career",
        "engineer",
        "important",
        "project",
        "exam",
        "college",
        "startup"
    ]

    MEDIUM_IMPORTANCE = [
        "gym",
        "fitness",
        "study",
        "coding",
        "python",
        "skill"
    ]

    @staticmethod
    def score(text):

        score = 0

        lower_text = text.lower()

        for word in ImportanceEngine.HIGH_IMPORTANCE:
            if word in lower_text:
                score += 30

        for word in ImportanceEngine.MEDIUM_IMPORTANCE:
            if word in lower_text:
                score += 15

        return min(score, 100)