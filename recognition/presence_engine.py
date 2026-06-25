class PresenceEngine:

    current_people = []

    @staticmethod
    def update(person):

        if person not in PresenceEngine.current_people:

            PresenceEngine.current_people.append(
                person
            )

    @staticmethod
    def get_all():

        return PresenceEngine.current_people