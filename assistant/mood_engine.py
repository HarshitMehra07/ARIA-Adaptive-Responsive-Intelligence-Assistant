class MoodEngine:

    @staticmethod
    def detect(emotion):

        moods = {

            "happy": "playful",

            "neutral": "normal",

            "stressed": "caring",

            "angry": "calm",

            "sad": "supportive"

        }

        return moods.get(
            emotion,
            "normal"
        )