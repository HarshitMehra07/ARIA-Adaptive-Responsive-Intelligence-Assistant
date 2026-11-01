import pytest
import time

from core.aria_core import AriaCore
from core.brain_state import BrainState
from core.cloud_model_client import CloudModelResponse, ProviderUnavailableError
from core.conversation_manager import ConversationManager
from core.context_manager import ContextManager
from core.offline_response_engine import OfflineResponseEngine
from memory.goal_tracker import GoalTracker
from memory.memory_manager import (
    MemoryManager,
    MemoryStoreError,
    UnsafeMemoryError,
)
from relationship.relationship_manager import RelationshipManager


class RecordingCloudClient:
    def __init__(self, text="Cloud response"):
        self.text = text
        self.calls = []

    def complete(self, messages, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs})
        return CloudModelResponse(text=self.text, model="mock-model", raw={})


def test_memory_save_search_update_list_and_delete():
    memory_id = MemoryManager.save_memory(
        "preference", "I prefer concise answers", importance=40
    )

    assert MemoryManager.find_memories("concise answers")[0]["id"] == memory_id
    assert MemoryManager.get_memory(memory_id)["content"] == "I prefer concise answers"

    assert MemoryManager.update_memory(
        memory_id,
        "I prefer detailed explanations",
        importance=60,
    )
    listed = MemoryManager.list_memories()
    assert listed[0]["content"] == "I prefer detailed explanations"
    assert listed[0]["importance"] == 60
    assert MemoryManager.delete_memory(memory_id)
    assert MemoryManager.get_memory(memory_id) is None


def test_repeated_exact_memory_updates_instead_of_duplicating():
    first_id = MemoryManager.save_memory("preference", "I prefer concise answers", 20)
    second_id = MemoryManager.save_memory("preference", "I prefer concise answers", 80)

    assert second_id == first_id
    assert len(MemoryManager.list_memories()) == 1
    assert MemoryManager.get_memory(first_id)["importance"] == 80
    assert MemoryManager.get_memory(first_id)["occurrence_count"] == 2


def test_memory_commands_save_list_update_and_forget():
    cloud = RecordingCloudClient()
    aria = AriaCore(cloud_client=cloud)

    response = aria.process_input("Remember that I prefer concise answers.")
    memory_id = aria.state.metadata["memory_saved_id"]
    assert "I'll remember that" in response
    assert cloud.calls == []

    response = aria.process_input("What do you remember about me?")
    assert f"#{memory_id} [preference] I prefer concise answers." in response

    response = aria.process_input(f"Update memory #{memory_id} to I prefer short answers.")
    assert "updated" in response
    assert MemoryManager.get_memory(memory_id)["content"] == "I prefer short answers."

    response = aria.process_input(f"Forget memory #{memory_id}")
    assert "deleted" in response
    assert MemoryManager.list_memories() == []


def test_memory_commands_forget_matching_text_and_all_memories():
    MemoryManager.save_memory("general", "I work at Acme Systems", 20)
    MemoryManager.save_memory("preference", "I prefer concise answers", 40)
    aria = AriaCore(cloud_client=RecordingCloudClient())

    response = aria.process_input("Forget Acme Systems")
    assert "forgot 1 matching saved memory" in response
    assert len(MemoryManager.list_memories()) == 1

    response = aria.process_input("Forget my preference for concise answers")
    assert "forgot 1 matching saved memory" in response
    assert MemoryManager.list_memories() == []

    MemoryManager.save_memory("general", "A fact for deletion", 10)
    response = aria.process_input("Forget all memories")
    assert "deleted 1 saved memory" in response
    assert MemoryManager.list_memories() == []


def test_user_preference_is_captured_but_ordinary_chat_is_not_saved():
    cloud = RecordingCloudClient("Thanks for telling me.")
    aria = AriaCore(cloud_client=cloud)

    aria.process_input("Hello ARIA")
    assert MemoryManager.list_memories() == []

    aria.process_input("I prefer concise, practical responses.")
    assert len(MemoryManager.list_memories()) == 1
    assert MemoryManager.list_memories()[0]["category"] == "preference"


def test_memory_is_retrieved_by_a_separate_core_instance():
    MemoryManager.save_memory("preference", "I prefer concise responses", 50)
    ConversationManager.clear()
    cloud = RecordingCloudClient()
    aria_after_restart = AriaCore(cloud_client=cloud)

    aria_after_restart.process_input("What response style do I prefer?")

    assert "I prefer concise responses" in aria_after_restart.state.active_memory_context
    system_prompt = cloud.calls[0]["messages"][0]["content"]
    assert "I prefer concise responses" in system_prompt


def test_goal_persists_separately_from_personal_memories():
    first_client = RecordingCloudClient()
    first_instance = AriaCore(cloud_client=first_client)
    first_instance.process_input("My goal is to become a data scientist")
    ConversationManager.clear()

    next_instance = AriaCore(cloud_client=RecordingCloudClient())
    next_instance.process_input("How can I achieve it?")

    assert next_instance.state.current_goal == "to become a data scientist"
    assert GoalTracker.get_active_goal() == "to become a data scientist"
    assert MemoryManager.get_all_memories() == []


@pytest.mark.parametrize(
    "content",
    [
        "OPENROUTER_API_KEY=sk-or-v1-abcdefghijklmnop",
        "password: hunter2",
        "my password is hunter2",
        "Bearer sk-or-v1-abcdefghijklmnop",
        "-----BEGIN RSA PRIVATE KEY-----",
    ],
)
def test_secret_like_content_is_never_saved(content):
    with pytest.raises(UnsafeMemoryError):
        MemoryManager.save_memory("general", content)
    assert MemoryManager.list_memories() == []


def test_memory_storage_failures_are_reported_without_crashing(monkeypatch, tmp_path):
    db_directory = tmp_path / "not-a-database-file"
    db_directory.mkdir()
    monkeypatch.setattr("memory.memory_manager.DB_NAME", str(db_directory))
    aria = AriaCore(cloud_client=RecordingCloudClient())

    response = aria.process_input("Remember that I prefer concise answers")

    assert "database problem" in response
    with pytest.raises(MemoryStoreError):
        MemoryManager.list_memories()


def test_memory_retrieval_does_not_override_current_request():
    MemoryManager.save_memory("preference", "I prefer concise answers", 50)
    cloud = RecordingCloudClient()
    aria = AriaCore(cloud_client=cloud)

    aria.process_input("Please give me a detailed explanation of neural networks")

    system_prompt = cloud.calls[0]["messages"][0]["content"]
    assert "current instructions override any saved memory" in system_prompt


def test_memory_privacy_levels_enforce_owner_and_explicit_sharing():
    private_id = MemoryManager.save_memory(
        "general", "Private journal detail", privacy_level="PRIVATE"
    )
    personal_id = MemoryManager.save_memory(
        "general", "Personal preference", privacy_level="PERSONAL"
    )
    shared_id = MemoryManager.save_memory(
        "general",
        "Shared project detail",
        privacy_level="SHARED",
        authorized_people=["friend"],
    )
    public_id = MemoryManager.save_memory(
        "general", "Public biography detail", privacy_level="PUBLIC"
    )

    friend_memories = MemoryManager.list_memories(requester_id="friend")
    friend_ids = {item["id"] for item in friend_memories}
    assert friend_ids == {shared_id, public_id}
    assert MemoryManager.get_memory(private_id, requester_id="friend") is None
    assert MemoryManager.get_memory(personal_id, requester_id="friend") is None
    assert not MemoryManager.delete_memory(private_id, requester_id="friend")
    assert MemoryManager.get_memory(private_id) is not None


def test_memory_commands_support_private_and_explicitly_shared_records():
    aria = AriaCore(cloud_client=RecordingCloudClient())

    aria.process_input("Remember privately that my journal is off limits.")
    private_id = aria.state.metadata["memory_saved_id"]
    private_memory = MemoryManager.get_memory(private_id)
    assert private_memory["privacy_level"] == "PRIVATE"

    aria.process_input("Remember to share with friend: Our project plan.")
    shared_id = aria.state.metadata["memory_saved_id"]
    assert MemoryManager.get_memory(shared_id)["privacy_level"] == "SHARED"
    assert MemoryManager.get_memory(shared_id, requester_id="friend")["content"] == (
        "Our project plan."
    )


def test_memory_capacity_is_bounded_and_reported(monkeypatch):
    monkeypatch.setattr(MemoryManager, "MAX_MEMORIES_PER_OWNER", 0)
    aria = AriaCore(cloud_client=RecordingCloudClient())

    response = aria.process_input("Remember that I prefer concise answers")

    assert "long-term memory is full" in response
    assert aria.state.metadata["memory_error"] == "capacity"
    assert MemoryManager.list_memories() == []


def test_conversation_history_isolated_between_speakers_and_private_requests_refused():
    ConversationManager.add_user_message("A private primary-user conversation")
    MemoryManager.save_memory(
        "general", "The primary user's private detail", privacy_level="PRIVATE"
    )
    client = RecordingCloudClient("Hello.")
    aria = AriaCore(cloud_client=client)

    aria.process_input(
        "Hello",
        sensory_data={
            "requester_id": "primary_user",
            "person_context": {
                "name": "Alice",
                "preferences": ["sensitive person profile"],
            },
        },
        requester_id="friend",
    )
    prompt = "\n".join(
        message["content"] for message in client.calls[0]["messages"]
    )
    assert "private primary-user conversation" not in prompt
    assert "sensitive person profile" not in prompt
    assert aria.state.conversation_history == []
    assert "private primary-user conversation" in "".join(
        turn["content"] for turn in ConversationManager.get_history()
    )

    response = aria.process_input(
        "What does Harshit say about me?", requester_id="friend"
    )
    assert "can't share private conversations" in response
    assert len(client.calls) == 1

    response = aria.process_input(
        "What do you remember about me?",
        sensory_data={"requester_id": "primary_user"},
        requester_id="friend",
    )
    assert "primary user's private detail" not in response


def test_relationship_profile_and_person_memory_are_connected(monkeypatch, tmp_path):
    relationship_db = tmp_path / "relationship-test.db"
    monkeypatch.setattr(
        "relationship.relationship_manager.DB_NAME", str(relationship_db)
    )
    profile = RelationshipManager.save_person(
        "Alice",
        nickname="Al",
        relationship_type="friend",
        preferences=["tea"],
        shared_interests=["hiking"],
        trust_level=70,
        privacy_boundaries=["do not share health details"],
        relationship_context="Met through a hiking group",
    )
    assert profile["nickname"] == "Al"
    assert profile["shared_interests"] == ["hiking"]
    assert profile["trust_level"] == 70

    MemoryManager.save_memory(
        "general",
        "Alice enjoys green tea",
        subject_person="Alice",
    )
    MemoryManager.save_memory("general", "I enjoy green tea")
    aria = AriaCore(cloud_client=RecordingCloudClient())

    aria.process_input("What do you remember about Alice?")

    assert aria.state.metadata["person_context"]["name"] == "Alice"
    assert aria.state.entities[0]["type"] == "person"
    assert aria.state.metadata["saved_memories"][0]["content"] == "Alice enjoys green tea"


def test_legacy_relationship_facades_share_persistent_profiles(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "relationship.relationship_manager.DB_NAME",
        str(tmp_path / "relationship-facade-test.db"),
    )
    from relationships.people_memory import PeopleMemory
    from relationships.relationship_engine import RelationshipEngine
    from relationships.social_graph import SocialGraph
    from relationships.trust_engine import TrustEngine
    from relationship.relationship_engine import RelationshipEngine as CoreRelationshipEngine

    RelationshipEngine.add("Morgan", "colleague")
    TrustEngine.update("Morgan", 75)
    PeopleMemory.remember("Morgan", "Prefers written project updates")
    SocialGraph.connect("Morgan", "Riley")
    CoreRelationshipEngine.interact("Morgan")

    assert RelationshipEngine.get("Morgan") == "colleague"
    assert TrustEngine.get("Morgan") == 75
    assert PeopleMemory.recall("Morgan") == ["Prefers written project updates"]
    assert SocialGraph.get_connections("Riley") == ["Morgan"]
    assert CoreRelationshipEngine.profile("Morgan")["bond"] == 1


def test_expired_short_term_context_is_summarized_and_removed():
    ConversationManager.add_user_message("I am working toward a robotics project")
    ConversationManager._history_timestamps[0] = (
        time.time() - ConversationManager.MAX_AGE_SECONDS - 1
    )

    assert ConversationManager.get_history() == []
    assert "robotics project" in ConversationManager.get_summary()


def test_context_tracks_new_topics_and_resolves_followups():
    ConversationManager.clear()

    ContextManager.resolve("How can I learn Python?")
    follow_up = ContextManager.resolve("How can I use it?")

    assert "Current topic is can I learn Python" in follow_up


def test_offline_assistance_is_bounded_and_can_explain_basic_python():
    state = BrainState(user_text="Explain a Python function")

    response = OfflineResponseEngine.respond(state, cloud_error="timeout")

    assert "timed out" in response
    assert "reusable code" in response
    assert "cloud-generated" not in response


def test_brain_uses_local_assistance_when_cloud_provider_is_unreachable():
    class UnavailableCloudClient:
        def complete(self, messages, **kwargs):
            raise ProviderUnavailableError("network unavailable")

    aria = AriaCore(cloud_client=UnavailableCloudClient())

    response = aria.process_input("Explain a Python function")

    assert "basic local explanation" in response
    assert "reusable code" in response
    assert aria.state.metadata["offline_mode"] is True
    assert aria.state.metadata["cloud_error"] == "provider_unavailable"
