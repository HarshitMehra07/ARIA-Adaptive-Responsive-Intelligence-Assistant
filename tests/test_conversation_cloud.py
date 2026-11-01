import pytest

from core.aria_core import AriaCore
from core.cloud_model_client import (
    AuthenticationError,
    CloudModelResponse,
    CloudTimeoutError,
    InvalidModelError,
    RateLimitError,
)
from core.conversation_manager import ConversationManager
from core.personality_engine import PersonalityMode


class RecordingCloudClient:
    def __init__(self, text="Cloud hello"):
        self.text = text
        self.calls = []

    def complete(self, messages, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs})
        return CloudModelResponse(text=self.text, model="mock-model", raw={})


class FailingCloudClient:
    def complete(self, messages, **kwargs):
        raise AuthenticationError(
            "OPENROUTER_API_KEY is missing or invalid. "
            "Set a full OpenRouter key in the local .env file."
        )


def test_chat_requests_use_cloud_client():
    ConversationManager.clear()
    client = RecordingCloudClient(text="Hello Harshit, I am ARIA.")
    aria = AriaCore(cloud_client=client)

    response = aria.process_input("Hello ARIA")

    assert response == "Hello Harshit, I am ARIA."
    assert len(client.calls) == 1
    messages = client.calls[0]["messages"]
    assert messages[0]["role"] == "system"
    assert messages[-1]["content"] == "Hello ARIA"
    assert aria.state.metadata.get("cloud_model") == "mock-model"


def test_ordinary_knowledge_question_uses_cloud_not_research():
    ConversationManager.clear()
    client = RecordingCloudClient(text="A neural network learns by adjusting its weights.")
    aria = AriaCore(cloud_client=client)

    response = aria.process_input("What is a neural network?")

    assert response == "A neural network learns by adjusting its weights."
    assert len(client.calls) == 1
    assert aria.state.planned_actions == ["generate_answer"]
    assert aria.state.metadata.get("cloud_model") == "mock-model"


def test_explanatory_question_uses_cloud_client():
    ConversationManager.clear()
    client = RecordingCloudClient(text="Training adjusts weights to reduce prediction error.")
    aria = AriaCore(cloud_client=client)

    response = aria.process_input("Explain how a neural network learns")

    assert response == "Training adjusts weights to reduce prediction error."
    assert len(client.calls) == 1
    assert aria.state.metadata.get("cloud_model") == "mock-model"


def test_explicit_web_research_is_not_fabricated_when_search_is_unavailable(monkeypatch):
    ConversationManager.clear()
    client = RecordingCloudClient(text="should not answer as researched")
    aria = AriaCore(cloud_client=client)

    def unexpected_search(*_args, **_kwargs):
        raise AssertionError("placeholder research must never be called")

    monkeypatch.setattr(aria.research_manager, "search_web", unexpected_search)
    response = aria.process_input("Search the web for recent neural network research")

    assert "TAVILY_API_KEY" in response
    assert "no search was performed" in response.lower()
    assert client.calls == []
    assert aria.state.planned_actions == ["research_unavailable"]


def test_chat_includes_memory_and_personality_in_system_prompt():
    ConversationManager.clear()
    client = RecordingCloudClient(text="Working on it.")
    aria = AriaCore(cloud_client=client)
    aria.current_personality = PersonalityMode.JARVIS
    aria.state = None
    aria.process_input("Hello")

    system = client.calls[0]["messages"][0]["content"]
    assert "JARVIS" in system
    assert "Personality mode: jarvis" in system


def test_goal_setting_still_uses_local_pipeline():
    ConversationManager.clear()
    client = RecordingCloudClient(text="should not be used")
    aria = AriaCore(cloud_client=client)

    response = aria.process_input("My goal is to become an AI Engineer")

    assert "AI Engineer" in response
    assert client.calls == []


def test_cloud_auth_error_is_returned_clearly():
    ConversationManager.clear()
    aria = AriaCore(cloud_client=FailingCloudClient())

    response = aria.process_input("Hello there")

    assert "authentication failed" in response
    assert "OPENROUTER_API_KEY" not in response
    assert aria.state.metadata.get("cloud_error") == "authentication_error"


def test_cloud_timeout_has_honest_user_facing_message():
    ConversationManager.clear()

    class TimedOutCloudClient:
        def complete(self, messages, **kwargs):
            raise CloudTimeoutError("request timed out")

    aria = AriaCore(cloud_client=TimedOutCloudClient())

    response = aria.process_input("Explain how a neural network learns")

    assert "timed out" in response
    assert "neural network" not in response
    assert aria.state.metadata.get("cloud_error") == "timeout"


@pytest.mark.parametrize(
    "error,response_text,error_type",
    [
        (RateLimitError("private provider details"), "rate limit", "rate_limit"),
        (InvalidModelError("private provider details"), "OPENROUTER_MODEL", "invalid_model"),
    ],
)
def test_cloud_rate_limit_and_invalid_model_are_reported_safely(
    error, response_text, error_type
):
    ConversationManager.clear()

    class FailingClient:
        def complete(self, messages, **kwargs):
            raise error

    aria = AriaCore(cloud_client=FailingClient())
    response = aria.process_input("Explain model routing")

    assert response_text.lower() in response.lower()
    assert "private provider details" not in response
    assert aria.state.metadata.get("cloud_error") == error_type


def test_credentials_are_redacted_from_cloud_requests_and_history():
    ConversationManager.clear()
    client = RecordingCloudClient("I can help with account security.")
    aria = AriaCore(cloud_client=client)
    secret = "my password is hunter2"

    aria.process_input(f"{secret}")

    sent_messages = "\n".join(
        message["content"] for message in client.calls[0]["messages"]
    )
    saved_history = "\n".join(
        turn["content"] for turn in ConversationManager.get_history()
    )
    assert "hunter2" not in sent_messages
    assert "hunter2" not in saved_history
    assert "[redacted secret]" in sent_messages
