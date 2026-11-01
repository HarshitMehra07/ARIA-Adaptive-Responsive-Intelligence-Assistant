class InterventionEngine:

    @staticmethod
    def intervene(activity):

        if activity == "phone":

            return (
                "Boss, focus on "
                "your work first."
            )

        if activity == "coding":

            return (
                "Boss, need help "
                "with that bug?"
            )

        return (
            "No intervention needed."
        )