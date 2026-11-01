from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class BrainState:
    """
    Represents the internal state of ARIA's brain during a single processing turn.
    """
    # Raw and processed input
    user_text: str = ""
    resolved_text: str = ""

    # NLU Results
    intent: str = "chat"
    sentiment: str = "neutral"
    entities: List[Dict[str, Any]] = field(default_factory=list)

    # Contextual Information
    current_topic: Optional[str] = None
    current_goal: Optional[str] = None
    active_memory_context: List[Any] = field(default_factory=list)

    # Personality and Emotion
    personality_mode: str = "professional"
    estimated_user_emotion: str = "neutral"
    aria_emotional_state: str = "stable"

    # Reasoning and Decision
    planned_actions: List[str] = field(default_factory=list)
    reasoning_log: List[str] = field(default_factory=list)

    # Output
    response_text: str = ""

    # History and Metadata
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def log_reasoning(self, step: str):
        self.reasoning_log.append(step)
