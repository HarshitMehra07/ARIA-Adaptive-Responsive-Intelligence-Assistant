from memory.intent_engine import IntentEngine
from memory.emotion_engine import EmotionEngine
from memory.entity_extractor import EntityExtractor
from memory.decision_engine import DecisionEngine
from memory.chat_brain import ChatBrain


class UnifiedBrain:

    @staticmethod
    def process(text):

        intent = IntentEngine.detect(text)

        emotion = EmotionEngine.detect(text)

        entities = EntityExtractor.extract(text)

        system = DecisionEngine.decide(
            intent
        )

        response = ChatBrain.chat(
            text
        )

        return {

            "intent": intent,

            "emotion": emotion,

            "entities": entities,

            "system": system,

            "response": response

        }