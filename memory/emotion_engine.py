class EmotionEngine:

    EMOTIONS = {

        "happy": [
            "happy",
            "great",
            "awesome",
            "excited",
            "fantastic"
        ],

        "sad": [
            "sad",
            "depressed",
            "upset",
            "hurt",
            "crying"
        ],

        "angry": [
            "angry",
            "mad",
            "furious",
            "annoyed"
        ],

        "stressed": [
            "stressed",
            "pressure",
            "overwhelmed",
            "anxious"
        ],

        "motivated": [
            "motivated",
            "focused",
            "determined",
            "disciplined"
        ]
    }

    @staticmethod
    def detect(text):

        lower = text.lower()

        for emotion, words in EmotionEngine.EMOTIONS.items():

            for word in words:

                if word in lower:
                    return emotion

        return "neutral"