class MemoryFilter:

    IMPORTANT_KEYWORDS = [
    "goal",
    "dream",
    "project",
    "study",
    "college",
    "career",
    "health",
    "gym",
    "exam",
    "important",
    "engineer",
    "ai",
    "machine learning",
    "skill",
    "job",
    "business",
    "startup",
    "achievement"
]

    @staticmethod
    def calculate_importance(text):

        score = 0

        text = text.lower()

        for keyword in MemoryFilter.IMPORTANT_KEYWORDS:
            if keyword in text:
                score += 20

        return min(score, 100)

    @staticmethod
    def should_store(text):

        score = MemoryFilter.calculate_importance(text)

        return score >= 40