class SchedulerEngine:

    @staticmethod
    def parse(text):

        lower = text.lower()

        if "30 minute" in lower:

            return 30

        if "1 hour" in lower:

            return 60

        if "2 hour" in lower:

            return 120

        return 0