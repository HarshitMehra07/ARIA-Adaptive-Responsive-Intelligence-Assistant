class PeopleDatabase:

    people = {}

    @staticmethod
    def add(name, relation):

        PeopleDatabase.people[
            name
        ] = relation

    @staticmethod
    def get(name):

        return PeopleDatabase.people.get(
            name,
            "Unknown"
        )

    @staticmethod
    def all():

        return PeopleDatabase.people