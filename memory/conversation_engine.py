from memory.nlu_engine import NLUEngine
from memory.response_engine import ResponseEngine


class ConversationEngine:

    @staticmethod
    def reply(text):

        intent = NLUEngine.detect_intent(
            text
        )

        response = ResponseEngine.generate(
            intent
        )

        return response