from core.brain_state import BrainState
from core.aria_identity import AriaIdentity
from core.capability_router import CapabilityRouter
import re

class IntentEngine:
    @staticmethod
    def process(state: BrainState):
        """
        Detect intent and entities from the resolved text.
        """
        original = state.user_text.strip()
        text = original.lower() # Use original text for intent to avoid context bleed

        route = CapabilityRouter.resolve(original)
        computer_command = (
            route.command if route and route.capability == "automation" else None
        )
        if (
            computer_command
            and computer_command.action == "cancel"
            and not state.metadata.get("automation_confirmation_pending")
        ):
            computer_command = None
        if computer_command:
            state.intent = "computer_control"
            state.metadata["computer_command"] = computer_command
            state.metadata["selected_capability"] = "automation"
            state.log_reasoning("Detected intent: computer_control")
            return

        if route and route.capability == "document_generation":
            state.intent = route.intent
            state.metadata["document_command"] = route.command
            state.metadata["selected_capability"] = route.capability
            state.log_reasoning(f"Detected intent: {state.intent}")
            return

        if IntentEngine._requests_private_disclosure(original):
            state.intent = "privacy_refusal"
            state.log_reasoning("Detected request for private conversation details.")
            return

        memory_intent = IntentEngine._detect_memory_intent(original)
        if memory_intent:
            state.intent = memory_intent[0]
            state.metadata["memory_command"] = memory_intent[1]
            state.log_reasoning(f"Detected intent: {state.intent}")
            return

        identity_response = AriaIdentity.answer(original)
        if identity_response:
            state.intent = "identity"
            state.metadata["identity_response"] = identity_response
            state.log_reasoning("Detected intent: identity")
            return

        if route and route.capability in {
            "website_safety",
            "web_research",
            "image_generation",
            "video_generation",
            "audio_generation",
            "capability_unavailable",
        }:
            state.intent = route.intent
            state.metadata["selected_capability"] = route.capability
            if route.target:
                state.metadata["safety_url"] = route.target
            state.log_reasoning(f"Selected capability: {route.capability}")
            return

        if "goal" in text or "i want to" in text:
            state.intent = "goal_setting"
        elif "remind" in text:
            state.intent = "reminder"
        elif "who" in text or "what" in text or "how" in text:
            state.intent = "question"
        elif "achieve" in text or "do it" in text:
            state.intent = "advice"
        else:
            state.intent = "chat"

        state.log_reasoning(f"Detected intent: {state.intent}")

    @staticmethod
    def _detect_memory_intent(text):
        lowered = text.lower().strip()

        if any(
            phrase in lowered
            for phrase in (
                "what do you remember",
                "what have you saved",
                "show saved memories",
                "list saved memories",
                "list my memories",
            )
        ):
            return "memory_list", {}

        if any(
            phrase in lowered
            for phrase in (
                "forget all memories",
                "forget everything you remember",
                "forget everything about me",
                "delete all memories",
                "delete all saved memories",
            )
        ):
            return "memory_delete_all", {}

        update_match = re.match(
            r"^(?:please\s+)?update\s+(?:saved\s+)?memory\s+#?(\d+)\s+(?:to|with)\s+(.+)$",
            text,
            re.IGNORECASE,
        )
        if update_match:
            return "memory_update", {
                "memory_id": int(update_match.group(1)),
                "content": update_match.group(2).strip(),
            }

        delete_match = re.match(
            r"^(?:please\s+)?(?:delete|forget)\s+(?:saved\s+)?memory\s+#?(\d+)\s*[.!]?",
            text,
            re.IGNORECASE,
        )
        if delete_match:
            return "memory_delete", {"memory_id": int(delete_match.group(1))}

        forget_match = re.match(r"^(?:please\s+)?forget\s+(?:that\s+)?(.+)$", text, re.IGNORECASE)
        if forget_match:
            return "memory_forget_match", {"query": forget_match.group(1).strip().rstrip(".!?")}

        remember_match = re.match(
            r"^(?:please\s+)?(?:remember(?:\s+that)?|save(?:\s+this)?|store(?:\s+this)?)"
            r"(?:\s+(?:in\s+)?memory)?\s*[:\-]?\s+(.+)$",
            text,
            re.IGNORECASE,
        )
        if remember_match:
            content = remember_match.group(1).strip()
            privacy_level = "PERSONAL"
            authorized_people = []
            private_match = re.match(
                r"^(?:privately|in confidence|for my eyes only|keep this private)"
                r"(?:\s+that)?\s*[:,\-]?\s*(.*)$",
                content,
                re.IGNORECASE,
            )
            shared_match = re.match(
                r"^(?:to\s+)?share(?:d)? with ([^:]+):\s*(.+)$",
                content,
                re.IGNORECASE,
            )
            if private_match:
                privacy_level = "PRIVATE"
                content = private_match.group(1).strip()
            elif shared_match:
                privacy_level = "SHARED"
                authorized_people = [
                    name.strip()
                    for name in shared_match.group(1).split(",")
                    if name.strip()
                ]
                content = shared_match.group(2).strip()
            if not content:
                return None
            category = "preference" if re.search(
                r"\b(prefer|favorite|favourite|like|love)\b", content, re.IGNORECASE
            ) else "general"
            return "memory_save", {
                "content": content,
                "category": category,
                "privacy_level": privacy_level,
                "authorized_people": authorized_people,
            }

        if re.match(r"^(?:i prefer|my preferred|my favorite|my favourite|i like|i love)\b", text, re.IGNORECASE):
            return "memory_preference", {"content": text, "category": "preference"}

        return None

    @staticmethod
    def _requests_private_disclosure(text):
        lowered = str(text or "").lower()
        patterns = (
            r"\bwhat\s+(?:does|did)\s+.+?\s+(?:say|tell|think)\s+(?:about|of)\s+me\b",
            r"\bwhat\s+(?:have you|did you)\s+(?:tell|say|share)\s+.+?\s+about me\b",
            r"\b(?:show|tell)\s+me\s+(?:the\s+)?(?:private|personal)\s+(?:conversation|messages?)\b",
            r"\bwhat\s+.+?\s+(?:told|shared)\s+you\s+in\s+private\b",
        )
        return any(re.search(pattern, lowered) for pattern in patterns)
