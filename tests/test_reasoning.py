from core.aria_core import ARIACore
from memory.reasoning_engine import ReasoningEngine

ARIACore.process(
    "My goal is to become an AI Engineer"
)

print(
    ReasoningEngine.answer(
        "How can I become successful in my career?"
    )
)