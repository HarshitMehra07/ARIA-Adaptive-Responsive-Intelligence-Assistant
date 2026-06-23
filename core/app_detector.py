import psutil


class AppDetector:

    @staticmethod
    def get_running_apps():

        apps = []

        for process in psutil.process_iter():

            try:
                apps.append(
                    process.name()
                )

            except:

                pass

        return list(set(apps))