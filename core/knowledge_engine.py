class KnowledgeEngine:

    knowledge = {}

    @classmethod
    def learn(cls, key, value, source="user"):

        normalized_key = key.lower().strip()

        cls.knowledge[normalized_key] = {
            "value": value,
            "source": source
        }

        return True

    @classmethod
    def get(cls, key):

        normalized_key = key.lower().strip()

        return cls.knowledge.get(
            normalized_key
        )

    @classmethod
    def search(cls, query):

        query = query.lower().strip()

        matches = []

        for key, data in cls.knowledge.items():

            if (
                query in key
                or key in query
            ):

                matches.append(
                    {
                        "key": key,
                        **data
                    }
                )

        return matches

    @classmethod
    def get_all(cls):

        return cls.knowledge.copy()

    @classmethod
    def clear(cls):

        cls.knowledge.clear()