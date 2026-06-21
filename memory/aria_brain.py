from memory.intent_engine import IntentEngine
from memory.emotion_engine import EmotionEngine
from memory.entity_extractor import EntityExtractor
from memory.preference_engine import PreferenceEngine
from memory.personality_engine import PersonalityEngine
from memory.decision_engine import DecisionEngine

from memory.reasoning_engine import ReasoningEngine
from memory.conversation_engine import ConversationEngine
from memory.goal_advisor import GoalAdvisor
from memory.mission_generator import MissionGenerator


class ARIABrain:

    @staticmethod
    def process(text):

        PreferenceEngine.learn(text)

        intent = IntentEngine.detect(text)

        emotion = EmotionEngine.detect(text)

        entities = EntityExtractor.extract(text)

        PreferenceEngine.learn(text)

        preferences = (
            PreferenceEngine.get_preferences()
        )

        personality = (
            PersonalityEngine.get_mode()
        )

        system = DecisionEngine.decide(intent)

        response = ""

        if system == "goal_system":

            response = (
                "Goal System Activated"
            )

        elif system == "progress_system":

            response = (
                "Progress System Activated"
            )

        elif system == "mission_system":

            response = (
                "Mission System Activated"
            )

        elif system == "reasoning_system":

            response = (
                ReasoningEngine.answer(text)
            )

        else:

            response = (
                ConversationEngine.reply(text)
            )

        return {        

            "intent": intent,

            "emotion": emotion,

            "entities": entities,

            "preferences": preferences,

            "personality": personality,

            "system": system,

            "response": response

        }