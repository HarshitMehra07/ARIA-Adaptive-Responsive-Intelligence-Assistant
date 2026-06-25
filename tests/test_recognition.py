from recognition.people_database import (
    PeopleDatabase
)

from recognition.face_registry import (
    FaceRegistry
)

from recognition.recognition_engine import (
    RecognitionEngine
)

print(
    "\n===== RECOGNITION =====\n"
)

PeopleDatabase.add(
    "Harshit",
    "Boss"
)

PeopleDatabase.add(
    "Mom",
    "Mother"
)

FaceRegistry.register(
    "face_1",
    "Harshit"
)

FaceRegistry.register(
    "face_2",
    "Mom"
)

print(
    RecognitionEngine.recognize(
        "face_1"
    )
)

print(
    RecognitionEngine.recognize(
        "face_2"
    )
)