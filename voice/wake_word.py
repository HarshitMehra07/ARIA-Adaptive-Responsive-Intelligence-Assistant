class WakeWord:

    WORDS = [

        "aria",

        "hey aria",

        "hello aria"

    ]

    @staticmethod
    def detect(text):

        lower = text.lower()

        for word in WakeWord.WORDS:

            if word in lower:

                return True

        return False