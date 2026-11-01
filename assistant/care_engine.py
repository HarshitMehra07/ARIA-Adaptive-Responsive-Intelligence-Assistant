class CareEngine:

    @staticmethod
    def care(activity):

        if activity == "coding":

            return (
                "Boss, don't forget "
                "to take breaks."
            )

        if activity == "studying":

            return (
                "Boss, stay focused."
            )

        if activity == "gaming":

            return (
                "Boss, have fun."
            )

        return (
            "Boss, take care."
        )