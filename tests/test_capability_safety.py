from __future__ import annotations

from core.aria_core import AriaCore
from core.capability_router import CapabilityRouter
from core.cloud_model_client import CloudModelResponse
from core.conversation_manager import ConversationManager
from document_generation.document_spec import DocumentFormat
from research.website_safety import WebsiteSafetyAnalyzer


class RecordingCloudClient:
    def __init__(self):
        self.calls = []

    def complete(self, messages, **_kwargs):
        self.calls.append(messages)
        return CloudModelResponse(text="A text response.", model="test-model", raw={})


def test_capability_router_selects_existing_and_unavailable_capabilities():
    presentation = CapabilityRouter.resolve(
        "Create a presentation about artificial intelligence"
    )
    research = CapabilityRouter.resolve("Please research recent AI developments")
    image = CapabilityRouter.resolve("Generate an image of a mountain lake")
    ordinary_chat = CapabilityRouter.resolve("Tell me about neural networks")

    assert presentation is not None
    assert presentation.capability == "document_generation"
    assert presentation.command.document_format is DocumentFormat.POWERPOINT
    assert research is not None and research.capability == "web_research"
    assert image is not None and image.intent == "capability_unavailable"
    assert image.capability == "image_generation"
    assert ordinary_chat is None


def test_website_safety_checks_are_cautious_and_do_not_claim_reputation_data():
    report = WebsiteSafetyAnalyzer.analyze(
        "http://paypal.example/login"
    )

    assert report.risk_level == "elevated"
    assert report.confidence == "limited"
    assert any("outside its official" in finding for finding in report.findings)
    assert "not a definitive safety verdict" in report.summary

    clear_report = WebsiteSafetyAnalyzer.analyze("https://docs.python.org/3/")
    assert clear_report.risk_level == "no_obvious_signals"
    assert clear_report.confidence == "limited"


def test_aria_routes_website_safety_without_calling_cloud_or_visiting_site():
    ConversationManager.clear()
    cloud = RecordingCloudClient()
    aria = AriaCore(cloud_client=cloud)

    response = aria.process_input("Is http://paypal.example/login safe?")

    assert aria.state.intent == "website_safety"
    assert aria.state.planned_actions == ["analyze_website_safety"]
    assert "elevated" in response
    assert "not a definitive safety verdict" in response
    assert "did not visit the site" in response
    assert not cloud.calls


def test_aria_does_not_claim_unsupported_media_generation_was_completed():
    ConversationManager.clear()
    cloud = RecordingCloudClient()
    aria = AriaCore(cloud_client=cloud)

    response = aria.process_input("Generate an image of a mountain lake")

    assert aria.state.intent == "capability_unavailable"
    assert aria.state.planned_actions == ["capability_unavailable"]
    assert "can’t generate images" in response
    assert "storyboard" in response
    assert not cloud.calls
