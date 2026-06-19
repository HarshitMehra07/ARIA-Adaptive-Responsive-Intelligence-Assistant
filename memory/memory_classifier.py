class MemoryClassifier:

    CAREER_WORDS = [
        "engineer",
        "job",
        "career",
        "college",
        "student",
        "degree",
        "ai",
        "developer"
    ]

    FITNESS_WORDS = [
        "gym",
        "fitness",
        "workout",
        "weight",
        "muscle",
        "protein"
    ]

    PROJECT_WORDS = [
        "project",
        "aria",
        "app",
        "startup",
        "business"
    ]

    @staticmethod
    def classify(text):

        lower_text = text.lower()

        for word in MemoryClassifier.CAREER_WORDS:
            if word in lower_text:
                return "career"

        for word in MemoryClassifier.FITNESS_WORDS:
            if word in lower_text:
                return "fitness"

        for word in MemoryClassifier.PROJECT_WORDS:
            if word in lower_text:
                return "project"

        return "general"