class ReminderEngine:

    reminders = []

    @staticmethod
    def add(task, time):

        ReminderEngine.reminders.append({

            "task": task,

            "time": time

        })

        print(
            "Reminder Added"
        )

    @staticmethod
    def get_all():

        return ReminderEngine.reminders