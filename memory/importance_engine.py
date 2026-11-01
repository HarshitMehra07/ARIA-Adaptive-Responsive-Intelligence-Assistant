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
    PREFERENCE_MARKERS = (
        "i prefer",
        "my preferred",
        "my favorite",
        "my favourite",
        "i like",
        "i love",
    )

    @staticmethod
    def score(
        text,
        *,
        explicit=False,
        repetitions=1,
        relationship=False,
        active_goal=False,
    ):

        score = 0

        lower_text = text.lower()

        for word in ImportanceEngine.HIGH_IMPORTANCE:
            if word in lower_text:
                score += 30

        for word in ImportanceEngine.MEDIUM_IMPORTANCE:
            if word in lower_text:
                score += 15

        if any(marker in lower_text for marker in ImportanceEngine.PREFERENCE_MARKERS):
            score += 20
        if explicit:
            score += 30
        if relationship:
            score += 20
        if active_goal:
            score += 15
        score += min(max(int(repetitions) - 1, 0) * 5, 20)

        return min(score, 100)