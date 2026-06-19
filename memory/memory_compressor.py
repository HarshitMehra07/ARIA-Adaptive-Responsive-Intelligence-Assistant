class MemoryCompressor:

    IMPORTANT_WORDS = [
        "goal",
        "career",
        "dream",
        "engineer",
        "student",
        "college",
        "project",
        "gym",
        "fitness",
        "ai",
        "coding",
        "python",
        "family",
        "friend",
        "relationship"
    ]

    @staticmethod
    def compress(memories):

        compressed = []

        seen = set()

        keyword_count = {}

        for memory in memories:

            text = memory.lower()

            if text in seen:
                continue

            seen.add(text)

            compressed.append(memory)

            for word in MemoryCompressor.IMPORTANT_WORDS:

                if word in text:

                    keyword_count[word] = (
                        keyword_count.get(word, 0) + 1
                    )

        summary = []

        for word, count in keyword_count.items():

            if count >= 3:

                summary.append(
                    f"User frequently talks about {word}"
                )

        return {
            "memories": compressed,
            "summary": summary
        }