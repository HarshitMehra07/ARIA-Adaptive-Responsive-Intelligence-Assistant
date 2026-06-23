from core.app_detector import AppDetector


class ActivityEngine:

    @staticmethod
    def analyze():

        apps = AppDetector.get_running_apps()

        if "Code.exe" in apps:

            return "coding"

        if "chrome.exe" in apps:

            return "browsing"

        if "spotify.exe" in apps:

            return "music"

        return "idle"