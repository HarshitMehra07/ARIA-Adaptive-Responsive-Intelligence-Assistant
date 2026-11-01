from core.brain_state import BrainState

class PersonalityMode:
    FRIENDLY = "friendly"
    PROFESSIONAL = "professional"
    COACH = "coach"
    JARVIS = "jarvis"
    STRICT = "strict"

class PersonalityEngine:
    PERSONAS = {
        "aria": {
            "gender": "female",
            "name": "ARIA",
            "traits": ["warm", "intelligent", "confident", "playful"]
        },
        "jarvis": {
            "gender": "male",
            "name": "JARVIS",
            "traits": ["calm", "precise", "sophisticated", "dry humor"]
        }
    }

    @staticmethod
    def process(state: BrainState):
        """
        Adjusts the state's response style based on personality mode and emotion.
        """
        mode = state.personality_mode or PersonalityMode.PROFESSIONAL
        emotion = state.estimated_user_emotion or "neutral"

        state.log_reasoning(f"Applying personality: {mode} (User emotion: {emotion})")

        # This will be used by the ResponseGenerator to tune the output
        if emotion == "stressed":
            state.metadata["tone_override"] = "comforting"
        elif emotion == "happy":
            state.metadata["tone_override"] = "enthusiastic"
        elif mode == PersonalityMode.JARVIS:
            state.metadata["tone_override"] = "efficient"
        else:
            state.metadata["tone_override"] = "balanced"
