class EmpathyEngine:

    @staticmethod
    def reply(emotion):

        if emotion == "stressed":

            return (
                "Boss, relax. "
                "We'll solve it together."
            )

        if emotion == "sad":

            return (
                "Boss, I am here."
            )

        if emotion == "angry":

            return (
                "Boss, take a breath "
                "before acting."
            )

        return (
            "Boss, everything looks good."
        )