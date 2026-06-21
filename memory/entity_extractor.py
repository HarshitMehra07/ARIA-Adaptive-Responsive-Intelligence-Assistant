class EntityExtractor:

    KNOWN_ENTITIES = [

        "python",
        "machine learning",
        "deep learning",
        "ai engineer",
        "data science",
        "gym",
        "college",
        "internship",
        "startup",
        "youtube"
    ]

    @staticmethod
    def extract(text):

        lower = text.lower()

        entities = []

        for entity in EntityExtractor.KNOWN_ENTITIES:

            if entity in lower:
                entities.append(entity)

        return entities