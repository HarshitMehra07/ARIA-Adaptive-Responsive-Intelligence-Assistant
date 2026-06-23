from core.activity_engine import ActivityEngine


class ScreenMonitor:

    @staticmethod
    def scan():

        activity = ActivityEngine.analyze()

        print(
            "Current Activity:",
            activity
        )

        return activity