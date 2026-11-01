import re


class OfflineResponseEngine:
    """Provide bounded local assistance without implying cloud-level capability."""

    EXPLANATIONS = {
        "class": (
            "A Python class is a blueprint for objects: it groups data and behavior. "
            "For example, `class Dog: pass` defines a minimal class."
        ),
        "dictionary": (
            "A Python dictionary stores values under keys, such as "
            "`person = {'name': 'Ada'}`; read a value with `person['name']`."
        ),
        "function": (
            "A Python function is reusable code defined with `def`; for example, "
            "`def double(value): return value * 2`."
        ),
        "list": (
            "A Python list is an ordered, changeable sequence, such as "
            "`numbers = [1, 2, 3]`; access its first item with `numbers[0]`."
        ),
        "loop": (
            "A loop repeats work. In Python, `for item in items:` runs its indented "
            "body once for each item."
        ),
        "variable": (
            "A variable is a name bound to a value, for example `count = 3`. "
            "Python determines the value's type at runtime."
        ),
    }

    @staticmethod
    def respond(state, *, cloud_error="provider_unavailable"):
        prefix = (
            "The cloud model request timed out. "
            if cloud_error == "timeout"
            else "The cloud model is unavailable. "
        )
        if state.active_memory_context:
            memories = [
                str(memory).strip()
                for memory in state.active_memory_context[:3]
                if str(memory).strip()
            ]
            memory_block = "; ".join(memories)
            return (
                prefix
                + "I can still use your local context. Relevant saved details: "
                + memory_block
                + ". They may be out of date; which should I use?"
            )

        text = str(state.user_text or "").lower()
        if any(phrase in text for phrase in ("explain", "what is", "teach me", "how does")):
            for topic, explanation in OfflineResponseEngine.EXPLANATIONS.items():
                if re.search(rf"\b{re.escape(topic)}s?\b", text):
                    return prefix + "Here is a basic local explanation: " + explanation
            return (
                prefix
                + "I can still help locally with your saved context, goals, and simple "
                "planning. For a new factual or coding explanation, paste the material "
                "or code and I can help organize what to examine; I can't provide a "
                "full cloud-generated answer while offline."
            )

        return (
            prefix
            + "I can still use local conversation context and saved memories, and help "
            "organize goals or next steps. What would be most useful?"
        )
