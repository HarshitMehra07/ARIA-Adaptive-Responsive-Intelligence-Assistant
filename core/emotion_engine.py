from core.brain_state import BrainState

class EmotionEngine:
    # Simple sentiment keywords for prototype
    STRESSED_KEYWORDS = ["stressed", "tired", "deadline", "worried", "anxious", "problem", "error"]
    HAPPY_KEYWORDS = ["great", "awesome", "solved", "happy", "excited", "good"]
    FRUSTRATED_KEYWORDS = ["hate", "annoying", "stupid", "broken", "useless"]

    @staticmethod
    def process(state: BrainState):
        """
        Estimates user emotion based on text and metadata.
        """
        text = state.user_text.lower()
        emotion = "neutral"

        if any(w in text for w in EmotionEngine.STRESSED_KEYWORDS):
            emotion = "stressed"
        elif any(w in text for w in EmotionEngine.HAPPY_KEYWORDS):
            emotion = "happy"
        elif any(w in text for w in EmotionEngine.FRUSTRATED_KEYWORDS):
            emotion = "frustrated"

        # Vision-based override (if vision service detected something)
        vision_emotion = state.metadata.get("vision_emotion")
        if vision_emotion and vision_emotion != "neutral":
            # Combine or override
            emotion = vision_emotion

        state.estimated_user_emotion = emotion
        state.log_reasoning(f"Estimated emotion: {emotion}")
