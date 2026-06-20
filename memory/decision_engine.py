class DecisionEngine:

    @staticmethod
    def decide(options):

        if not options:

            return "No options provided"

        return options[0]