from core.screen_monitor import ScreenMonitor


class ProactiveEngine:

    @staticmethod
    def think():

        activity = ScreenMonitor.scan()

        if activity == "coding":

            return (
                "Boss, need help "
                "with your code?"
            )

        if activity == "browsing":

            return (
                "Boss, stay focused."
            )

        if activity == "music":

            return (
                "Nice playlist, Boss."
            )

        return (
            "Everything looks good."
        )