from recognition.people_database import (
    PeopleDatabase
)


class GreetingEngine:

    @staticmethod
    def greet(person):

        relation = PeopleDatabase.get(
            person
        )

        greetings = {

            "Mother":
            "Hello Mom ❤️",

            "Father":
            "Hello Dad ❤️",

            "Friend":
            "Hello friend 😊",

            "Boss":
            "Hello Boss 🔥"
        }

        return greetings.get(
            relation,
            f"Hello {person}"
        )