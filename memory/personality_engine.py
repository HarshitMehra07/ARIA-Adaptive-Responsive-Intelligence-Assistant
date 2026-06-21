class PersonalityEngine:

    MODES = {

        "friendly":
        "warm and supportive",

        "coach":
        "strict and goal focused",

        "professional":
        "formal and precise",

        "mentor":
        "experienced guide",

        "motivator":
        "high energy and inspiring",

        "analyst":
        "logical and data driven",

        "companion":
        "casual and conversational"
    }

    current_mode = "coach"

    @staticmethod
    def set_mode(mode):

        if mode in PersonalityEngine.MODES:

            PersonalityEngine.current_mode = mode

            return True

        return False

    @staticmethod
    def get_mode():

        return PersonalityEngine.current_mode