from core.brain_state import BrainState
from core.capability_router import requests_web_research
from research.research_manager import ResearchManager

class ReasoningEngine:
    @staticmethod
    def process(state: BrainState, research_available=None):
        """
        Combine context, memory, and intent to decide on actions.
        """
        state.log_reasoning("Starting reasoning process...")

        # 1. Intent-based actions
        if state.intent == "computer_control":
            state.planned_actions.append("computer_control")

        elif state.intent == "memory_save":
            state.planned_actions.append("save_memory")

        elif state.intent == "memory_preference":
            state.planned_actions.append("capture_preference")

        elif state.intent == "memory_list":
            state.planned_actions.append("list_memories")

        elif state.intent == "memory_delete":
            state.planned_actions.append("delete_memory")

        elif state.intent == "memory_delete_all":
            state.planned_actions.append("delete_all_memories")

        elif state.intent == "memory_forget_match":
            state.planned_actions.append("forget_memories")

        elif state.intent == "memory_update":
            state.planned_actions.append("update_memory")

        elif state.intent == "identity":
            state.planned_actions.append("identity_response")

        elif state.intent == "privacy_refusal":
            state.planned_actions.append("protect_private_conversation")

        elif state.intent == "website_safety":
            state.planned_actions.append("analyze_website_safety")

        elif state.intent == "capability_unavailable":
            state.planned_actions.append("capability_unavailable")

        elif state.intent.startswith("document_"):
            state.planned_actions.append(state.intent)

        elif ReasoningEngine._requests_web_research(state.user_text):
            available = (
                ResearchManager().has_live_search()
                if research_available is None
                else research_available
            )
            if available:
                state.planned_actions.append("search_web")
            else:
                state.planned_actions.append("research_unavailable")

        elif state.intent == "goal_setting":
            state.planned_actions.append("store_goal")
            state.planned_actions.append("acknowledge_goal")

        elif state.intent == "question":
            # General questions use the configured response-generation pipeline.
            state.planned_actions.append("generate_answer")

        elif state.intent == "advice":
            state.planned_actions.append("provide_guidance")

        state.log_reasoning(f"Planned actions: {state.planned_actions}")

    @staticmethod
    def _requests_web_research(text: str) -> bool:
        return requests_web_research(text)
