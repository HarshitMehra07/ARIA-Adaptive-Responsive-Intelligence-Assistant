import re

from core.conversation_manager import ConversationManager


class ContextManager:

    FOLLOW_UP_PATTERNS = [
        "how can i achieve it",
        "how do i achieve it",
        "how can i do it",
        "how do i do it",
        "how can i learn it",
        "how do i learn it",
        "what about it",
        "explain it",
        "tell me more",
    ]

    GOAL_PATTERNS = [
        "my goal is ",
        "i want to become ",
        "i want to be ",
        "i want to learn ",
        "i am planning to ",
        "i'm planning to ",
    ]
    TOPIC_PATTERNS = (
        r"^(?:tell me about|explain|what is|what are|who is|teach me about|help me with)\s+(.+)$",
        r"^(?:i am interested in|i'm interested in|i am learning|i'm learning|let's discuss)\s+(.+)$",
        r"^how\s+(.+)$",
    )

    @staticmethod
    def detect_goal(text):

        lower = text.lower()

        for pattern in ContextManager.GOAL_PATTERNS:

            if pattern in lower:

                index = lower.find(pattern)

                goal = text[
                    index + len(pattern):
                ].strip()

                # Clean up punctuation
                if goal.endswith("."):
                    goal = goal[:-1]

                if goal:
                    return goal

        return None

    @staticmethod
    def resolve(text, session_id=None):
        """
        Resolves pronouns and context based on conversation history and goals.
        """
        clean_text = text.strip()
        lower = clean_text.lower()

        # Check for new goals
        goal = ContextManager.detect_goal(clean_text)

        if goal:
            if session_id is None:
                ConversationManager.set_goal(goal)
                ConversationManager.set_topic(goal)
            else:
                ConversationManager.set_goal(goal, session_id)
                ConversationManager.set_topic(goal, session_id)
            return clean_text

        # Context Resolution
        current_goal = (
            ConversationManager.get_goal()
            if session_id is None
            else ConversationManager.get_goal(session_id)
        )
        current_topic = (
            ConversationManager.get_topic()
            if session_id is None
            else ConversationManager.get_topic(session_id)
        )

        # Resolve anaphoric follow-ups without treating every "how" question as one.
        is_follow_up = any(p in lower for p in ContextManager.FOLLOW_UP_PATTERNS)
        if (current_goal or current_topic) and re.search(
            r"\b(?:it|that|this|they|them)\b", lower
        ):
            is_follow_up = True
        if current_topic and lower.rstrip("?.! ") in ("why", "how"):
            is_follow_up = True

        if is_follow_up and (current_goal or current_topic):
            context = current_goal or current_topic
            return f"{clean_text} (Context: Current topic is {context})"

        if " it" in lower and current_topic:
            # Replace "it" with the topic for the NLU layer to understand better
            # This is a simple replacement, could be more sophisticated
            resolved = clean_text.replace(" it", f" {current_topic}")
            resolved = resolved.replace(" It", f" {current_topic}")
            return resolved

        if not is_follow_up:
            for pattern in ContextManager.TOPIC_PATTERNS:
                match = re.match(pattern, clean_text, re.IGNORECASE)
                if match:
                    topic = match.group(1).strip().rstrip(".!?")
                    if topic:
                        if session_id is None:
                            ConversationManager.set_topic(topic)
                        else:
                            ConversationManager.set_topic(topic, session_id)
                    break

        return clean_text
