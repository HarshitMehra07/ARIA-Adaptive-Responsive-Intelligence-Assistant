class PreferenceEngine:

    preferences = {

        "likes": [],
        "dislikes": []
    }

    @staticmethod
    def learn(text):

        lower = text.lower()

        if "i like" in lower:

            item = text.replace("I like", "").strip()

            PreferenceEngine.preferences[
                "likes"
            ].append(item)

        if "i dislike" in lower:

            item = text.replace(
                "I dislike",
                ""
            ).strip()

            PreferenceEngine.preferences[
                "dislikes"
            ].append(item)

    @staticmethod
    def get_preferences():

        return PreferenceEngine.preferences
    
    @staticmethod
    def extract(text):

       PreferenceEngine.learn(text)

       return (
        PreferenceEngine.get_preferences()
    )