class ConversationMemory:

    history = []

    @staticmethod
    def add(message):

        ConversationMemory.history.append(
            message
        )

    @staticmethod
    def get_history():

        return ConversationMemory.history

    @staticmethod
    def get_last():

        if ConversationMemory.history:

            return ConversationMemory.history[-1]

        return None