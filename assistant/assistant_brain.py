from assistant.mood_engine import MoodEngine
from assistant.care_engine import CareEngine
from assistant.empathy_engine import EmpathyEngine
from assistant.intervention_engine import (
    InterventionEngine
)


class AssistantBrain:

    @staticmethod
    def think(
        emotion,
        activity
    ):

        mood = MoodEngine.detect(
            emotion
        )

        care = CareEngine.care(
            activity
        )

        empathy = (
            EmpathyEngine.reply(
                emotion
            )
        )

        intervention = (
            InterventionEngine.intervene(
                activity
            )
        )

        return {

            "mood": mood,

            "care": care,

            "empathy": empathy,

            "intervention": intervention

        }