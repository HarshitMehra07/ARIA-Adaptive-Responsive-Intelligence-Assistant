from recognition.face_registry import (
    FaceRegistry
)

from recognition.people_database import (
    PeopleDatabase
)

from recognition.presence_engine import (
    PresenceEngine
)

from recognition.greeting_engine import (
    GreetingEngine
)


class RecognitionEngine:

    @staticmethod
    def recognize(face_id):

        person = FaceRegistry.identify(
            face_id
        )

        if not person:

            return "Unknown Person"

        PresenceEngine.update(
            person
        )

        return GreetingEngine.greet(
            person
        )