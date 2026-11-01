import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.aria_core import AriaCore
from core.cloud_model_client import CloudModelResponse
from core.personality_engine import PersonalityMode
from core.conversation_manager import ConversationManager
from automation.models import ActionResult


class FakeCloudClient:
    def complete(self, messages, **kwargs):
        user_text = messages[-1]["content"]
        system_text = messages[0]["content"] if messages else ""
        if "JARVIS" in system_text:
            text = "At your service. Cloud status check complete."
        else:
            text = f"Acknowledged: {user_text}"
        return CloudModelResponse(text=text, model="mock-model", raw={})


class FakeComputerUseService:
    def handle_command(self, command):
        assert command.action == "execute"
        assert command.plan.actions[0].target == "browser"
        return ActionResult(
            operation="open_application",
            attempted=True,
            verified=True,
            details={
                "steps": [{"application": "Microsoft Edge"}],
                "completed_steps": 1,
            },
        )


def test_full_system_features():
    print("\n--- Running ARIA Full System Integration Test ---")
    aria = AriaCore(
        cloud_client=FakeCloudClient(),
        computer_use_service=FakeComputerUseService(),
    )
    ConversationManager.clear()

    # 1. Personality & Emotion Test
    print("\nTest 1: Personality & Emotion...")
    aria.state = None # Reset
    response1 = aria.process_input("I'm so stressed about my project.")
    print(f"ARIA (Stressed/Default): {response1}")
    assert "project" in response1

    # 2. Explicit web research must not present placeholders as real results.
    print("\nTest 2: Web Research...")
    response2 = aria.process_input("Search the web for the latest version of Python")
    print(f"ARIA (Researching): {response2}")
    assert "TAVILY_API_KEY" in response2
    assert "no search was performed" in response2.lower()

    # 3. Content Generation Test
    print("\nTest 3: Content Generation...")
    response3 = aria.process_input("Generate some python code for a calculator.")
    print(f"ARIA (Generating): {response3}")
    assert "Acknowledged: Generate some python code" in response3

    # 4. Automation Test
    print("\nTest 4: Automation...")
    response4 = aria.process_input("Open my browser.")
    print(f"ARIA (Automating): {response4}")
    assert response4 == "Opened or focused Microsoft Edge."
    assert aria.state.planned_actions == ["computer_control"]

    # 5. JARVIS Mode Test
    print("\nTest 5: JARVIS Mode...")
    aria.current_personality = PersonalityMode.JARVIS
    response5 = aria.process_input("Status check.")
    print(f"ARIA (JARVIS): {response5}")
    assert "At your service" in response5

    print("\n--- Full System Integration Test Passed! ---")

if __name__ == "__main__":
    try:
        test_full_system_features()
    except Exception as e:
        print(f"Test Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
