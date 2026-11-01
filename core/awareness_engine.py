from vision.vision_brain import VisionBrain

from assistant.assistant_brain import (
    AssistantBrain
)


class AwarenessEngine:

    @staticmethod
    def observe():

        vision = VisionBrain.analyze()

        emotion = vision.get(
            "emotion",
            "neutral"
        )

        activity = "coding"

        assistant = AssistantBrain.think(

            emotion,

            activity

        )

        return {

            "vision": vision,

            "assistant": assistant

        }