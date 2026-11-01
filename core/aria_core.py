import re

from core.brain_state import BrainState
from core.cloud_model_client import CloudModelClient, CloudModelError
from core.context_manager import ContextManager
from core.intent_engine import IntentEngine
from core.reasoning_engine import ReasoningEngine
from core.response_generator import ResponseGenerator
from core.conversation_manager import ConversationManager
from core.offline_response_engine import OfflineResponseEngine
from core.emotion_engine import EmotionEngine
from core.personality_engine import PersonalityEngine
from memory.memory_recall import MemoryRecall
from memory.importance_engine import ImportanceEngine
from memory.entity_extractor import EntityExtractor
from memory.profile_builder import ProfileBuilder
from memory.goal_tracker import GoalTracker
from memory.memory_manager import (
    MemoryCapacityError,
    MemoryManager,
    MemoryStoreError,
    UnsafeMemoryError,
    redact_secrets,
)
from relationship.relationship_manager import RelationshipManager
from research.research_manager import ResearchError, ResearchManager
from research.website_safety import WebsiteSafetyAnalyzer
from automation.automation_controller import AutomationController
from automation.computer_use import ComputerUseService
from document_generation.document_service import DocumentGenerationError, DocumentService
from document_generation.file_manager import FileManagementError

class AriaCore:
    SENSORY_RESERVED_KEYS = {
        "requester_id",
        "person_context",
        "conversation_summary",
        "memory_command",
        "active_memory_context",
        "saved_memories",
        "memory_saved_id",
        "memory_error",
        "cloud_error",
        "cloud_model",
        "offline_mode",
    }

    def __init__(
        self,
        cloud_client=None,
        research_manager=None,
        document_service=None,
        computer_use_service=None,
    ):
        self.state = None
        self.current_personality = "professional"
        self.cloud_client = cloud_client if cloud_client is not None else CloudModelClient.from_env()
        self.research_manager = research_manager or ResearchManager()
        self.document_service = document_service or DocumentService(
            cloud_client=self.cloud_client,
            research_manager=self.research_manager,
        )
        self.computer_use_service = (
            computer_use_service
            if computer_use_service is not None
            else ComputerUseService()
        )

    def process_input(
        self,
        user_input: str,
        sensory_data: dict = None,
        *,
        requester_id: str = "primary_user",
    ) -> str:
        """
        The main processing loop for ARIA.
        """
        requester_id = str(requester_id or "primary_user").strip()
        if not requester_id:
            requester_id = "primary_user"
        session_id = None if requester_id == "primary_user" else requester_id

        # 1. Initialize State
        self.state = BrainState(user_text=user_input)
        self.state.personality_mode = self.current_personality
        self.state.conversation_history = (
            ConversationManager.get_history()
            if session_id is None
            else ConversationManager.get_history(session_id)
        )
        if sensory_data:
            self.state.metadata.update(
                {
                    key: value
                    for key, value in sensory_data.items()
                    if key not in self.SENSORY_RESERVED_KEYS
                }
            )
        self.state.metadata["requester_id"] = requester_id
        self.state.log_reasoning("Loop started: State initialized.")

        # Restore the last active goal from SQLite when a new process has no
        # short-term conversation goal in memory.
        if session_id is None and ConversationManager.get_goal() is None:
            try:
                persisted_goal = GoalTracker.get_active_goal()
            except MemoryStoreError:
                persisted_goal = None
                self.state.metadata["goal_error"] = "storage_error"
            if persisted_goal:
                ConversationManager.set_goal(persisted_goal)
                ConversationManager.set_topic(persisted_goal)

        # 2. Perception & Context Resolution
        safe_input = redact_secrets(user_input)
        self.state.resolved_text = ContextManager.resolve(safe_input, session_id)
        self.state.current_goal = (
            ConversationManager.get_goal()
            if session_id is None
            else ConversationManager.get_goal(session_id)
        )
        self.state.current_topic = (
            ConversationManager.get_topic()
            if session_id is None
            else ConversationManager.get_topic(session_id)
        )
        self.state.metadata["conversation_summary"] = ConversationManager.get_summary(
            session_id
        )

        # 3. Emotion & Personality Assessment
        EmotionEngine.process(self.state)
        PersonalityEngine.process(self.state)

        # 4. Intent & Entity Understanding
        self.state.metadata["automation_confirmation_pending"] = bool(
            getattr(self.computer_use_service, "has_pending_confirmation", False)
        )
        IntentEngine.process(self.state)
        recognized_entities = EntityExtractor.extract(safe_input)
        self.state.entities.extend(
            {"type": "topic", "name": entity}
            for entity in recognized_entities
        )

        # 5. Knowledge & Memory Recall
        person = None
        try:
            if session_id is None:
                person = RelationshipManager.find_person_mentioned(safe_input)
        except MemoryStoreError:
            self.state.metadata["relationship_error"] = "storage_error"
        if person:
            self.state.metadata["person_context"] = person
            self.state.entities.append(
                {
                    "type": "person",
                    "name": person["name"],
                    "relationship": person["relationship_type"],
                }
            )
        if self.state.current_goal:
            self.state.entities.append(
                {"type": "goal", "value": self.state.current_goal}
            )
        recent_context = [
            turn.get("content", "")
            for turn in self.state.conversation_history[-4:]
            if turn.get("role") == "user"
        ]
        memory_query = " ".join(
            str(part)
            for part in (
                self.state.resolved_text,
                person["name"] if person else "",
                *recognized_entities,
                self.state.current_goal or "",
                *recent_context,
            )
            if part
        )
        try:
            if session_id is None:
                self.state.active_memory_context = MemoryRecall.recall(memory_query)
            else:
                self.state.active_memory_context = MemoryRecall.recall(
                    memory_query,
                    requester_id=requester_id,
                    subject_person=person["name"] if person else None,
                    current_goal=self.state.current_goal,
                    recent_context=recent_context,
                )
        except MemoryStoreError:
            self.state.active_memory_context = []
            self.state.metadata["memory_error"] = "storage_error"

        # 6. Reasoning & Decision
        ReasoningEngine.process(
            self.state,
            research_available=self.research_manager.has_live_search(),
        )

        # 7. Action Execution
        self.execute_actions()

        # 8. Response Generation
        try:
            ResponseGenerator.process(
                self.state,
                cloud_client=self.cloud_client,
                research_manager=self.research_manager,
            )
        except CloudModelError as error:
            if error.error_type in ("provider_unavailable", "timeout"):
                self.state.response_text = OfflineResponseEngine.respond(
                    self.state,
                    cloud_error=error.error_type,
                )
                self.state.log_reasoning(
                    f"Cloud unavailable; local response used ({error.error_type})."
                )
                self.state.metadata["cloud_error"] = error.error_type
                self.state.metadata["offline_mode"] = True
            else:
                self._set_cloud_error_response(error)

        # 9. Final Updates
        ConversationManager.add_user_message(
            redact_secrets(user_input), session_id
        )
        if "computer_control" not in self.state.planned_actions:
            ConversationManager.add_assistant_message(
                self.state.response_text, session_id
            )

        return self.state.response_text

    def _set_cloud_error_response(self, error):
        messages = {
            "authentication_error": (
                "I couldn't use the configured cloud model because authentication failed. "
                "Check the OpenRouter configuration and try again."
            ),
            "timeout": "The cloud model request timed out. Please try again.",
            "provider_unavailable": (
                "The cloud model provider is unavailable right now. Please try again later."
            ),
            "rate_limit": "The cloud model rate limit was reached. Please try again later.",
            "invalid_model": "The configured cloud model is unavailable. Check OPENROUTER_MODEL and try again.",
        }
        self.state.response_text = messages.get(
            error.error_type,
            "I couldn't get a response from the configured cloud model. Please try again.",
        )
        self.state.log_reasoning(f"Cloud model error: {error.error_type}")
        self.state.metadata["cloud_error"] = error.error_type

    def execute_actions(self):
        """
        Executes the actions decided by the ReasoningEngine.
        """
        for action in self.state.planned_actions:
            if action == "computer_control":
                command = self.state.metadata.get("computer_command")
                result = self.computer_use_service.handle_command(command)
                if result is None:
                    self.state.metadata["computer_use_error"] = (
                        "The computer action could not be parsed consistently."
                    )
                else:
                    self.state.metadata["computer_use_result"] = result
                self.state.log_reasoning(
                    f"Action: Computer control handled ({getattr(command, 'action', 'unknown')})."
                )

            elif action == "document_generate":
                command = self.state.metadata.get("document_command")
                source_text = next(
                    (
                        turn["content"]
                        for turn in reversed(self.state.conversation_history)
                        if turn.get("role") == "assistant" and turn.get("content")
                    ),
                    None,
                )
                try:
                    result = self.document_service.create_from_request(
                        self.state.resolved_text or self.state.user_text,
                        command.document_format,
                        source_text=source_text,
                    )
                    self.state.metadata["document_result"] = result
                    self.state.log_reasoning("Action: Document generated and validated.")
                except CloudModelError as error:
                    self.state.metadata["document_error"] = "cloud_provider"
                    self.state.metadata["cloud_error"] = error.error_type
                except ResearchError as error:
                    self.state.metadata["document_error"] = error.error_type
                except FileManagementError as error:
                    self.state.metadata["document_error"] = "file_management"
                    self.state.metadata["document_error_message"] = str(error)
                except DocumentGenerationError as error:
                    self.state.metadata["document_error"] = "generation_failed"
                    self.state.metadata["document_error_message"] = str(error)

            elif action == "document_list":
                try:
                    self.state.metadata["generated_files"] = (
                        self.document_service.list_generated_files()
                    )
                except FileManagementError as error:
                    self.state.metadata["document_error"] = "file_management"
                    self.state.metadata["document_error_message"] = str(error)

            elif action == "document_summarize":
                path = self.state.metadata.get("selected_document_path")
                if not path:
                    match = re.search(
                        r"(?P<path>(?:[A-Za-z]:[\\/]|\.{1,2}[\\/])[^\"\r\n]*\."
                        r"(?:txt|md|pdf|docx|xlsx|pptx))",
                        self.state.user_text,
                        re.IGNORECASE,
                    )
                    path = match.group("path").rstrip(" .,!?:;") if match else None
                if not path:
                    self.state.metadata["document_error"] = "selection_required"
                else:
                    try:
                        summary, partial = self.document_service.summarize_document(path)
                        self.state.metadata["document_summary"] = summary
                        self.state.metadata["document_partial"] = partial
                    except FileManagementError as error:
                        self.state.metadata["document_error"] = "file_management"
                        self.state.metadata["document_error_message"] = str(error)

            elif action == "document_unsupported":
                self.state.metadata["document_error"] = "unsupported_format"

            elif action == "store_goal":
                try:
                    requester_id = self.state.metadata.get("requester_id", "primary_user")
                    session_id = None if requester_id == "primary_user" else requester_id
                    goal = ConversationManager.get_goal(session_id) or ContextManager.detect_goal(
                        self.state.resolved_text
                    ) or self.state.resolved_text
                    if session_id is None:
                        GoalTracker.set_active_goal(goal)
                        ProfileBuilder.update_profile(self.state.resolved_text)
                    self.state.log_reasoning("Action: Goal stored.")
                except UnsafeMemoryError:
                    self.state.metadata["goal_error"] = "unsafe_content"
                except MemoryStoreError:
                    self.state.metadata["goal_error"] = "storage_error"
                    self.state.log_reasoning("Goal storage failed.")

            elif action in ("save_memory", "capture_preference"):
                command = self.state.metadata.get("memory_command", {})
                content = command.get("content", "")
                category = command.get("category", "general")
                try:
                    memory_id = MemoryManager.save_memory(
                        category,
                        content,
                        ImportanceEngine.score(
                            content,
                            explicit=self.state.intent == "memory_save",
                            relationship=bool(
                                self.state.metadata.get("person_context")
                            ),
                            active_goal=bool(self.state.current_goal and self.state.current_goal.lower() in content.lower()),
                        ),
                        privacy_level=command.get("privacy_level", "PERSONAL"),
                        owner_id=self.state.metadata.get("requester_id", "primary_user"),
                        subject_person=(
                            self.state.metadata.get("person_context", {}).get("name")
                            if self.state.metadata.get("person_context")
                            else None
                        ),
                        authorized_people=command.get("authorized_people", ()),
                    )
                    self.state.metadata["memory_saved_id"] = memory_id
                    self.state.log_reasoning("Action: Persistent memory stored.")
                except UnsafeMemoryError:
                    self.state.metadata["memory_error"] = "unsafe_content"
                except MemoryCapacityError:
                    self.state.metadata["memory_error"] = "capacity"
                except MemoryStoreError:
                    self.state.metadata["memory_error"] = "storage_error"

            elif action == "list_memories":
                try:
                    self.state.metadata["saved_memories"] = MemoryManager.list_memories(
                        requester_id=self.state.metadata.get("requester_id", "primary_user"),
                        subject_person=(
                            self.state.metadata.get("person_context", {}).get("name")
                            if self.state.metadata.get("person_context")
                            else None
                        ),
                    )
                except MemoryStoreError:
                    self.state.metadata["memory_error"] = "storage_error"

            elif action == "delete_memory":
                command = self.state.metadata.get("memory_command", {})
                try:
                    self.state.metadata["memory_deleted"] = MemoryManager.delete_memory(
                        command.get("memory_id"),
                        requester_id=self.state.metadata.get("requester_id", "primary_user"),
                    )
                except (MemoryStoreError, TypeError, ValueError):
                    self.state.metadata["memory_error"] = "storage_error"

            elif action == "delete_all_memories":
                try:
                    self.state.metadata["memory_deleted_count"] = MemoryManager.delete_all_memories(
                        requester_id=self.state.metadata.get("requester_id", "primary_user")
                    )
                except MemoryStoreError:
                    self.state.metadata["memory_error"] = "storage_error"

            elif action == "forget_memories":
                command = self.state.metadata.get("memory_command", {})
                try:
                    self.state.metadata["memory_deleted_count"] = MemoryManager.forget_memories(
                        command.get("query", ""),
                        requester_id=self.state.metadata.get("requester_id", "primary_user"),
                    )
                except MemoryStoreError:
                    self.state.metadata["memory_error"] = "storage_error"

            elif action == "update_memory":
                command = self.state.metadata.get("memory_command", {})
                content = command.get("content", "")
                try:
                    self.state.metadata["memory_updated"] = MemoryManager.update_memory(
                        command.get("memory_id"),
                        content,
                        importance=ImportanceEngine.score(content),
                        requester_id=self.state.metadata.get("requester_id", "primary_user"),
                    )
                except UnsafeMemoryError:
                    self.state.metadata["memory_error"] = "unsafe_content"
                except (MemoryStoreError, TypeError, ValueError):
                    self.state.metadata["memory_error"] = "storage_error"

            elif action == "search_web":
                try:
                    results = self.research_manager.search_web(self.state.resolved_text)
                    self.state.metadata["search_results"] = results
                    self.state.log_reasoning("Action: Web research performed.")
                except ResearchError as error:
                    self.state.metadata["research_error"] = error.error_type
                    self.state.log_reasoning(f"Web research error: {error.error_type}")

            elif action == "analyze_website_safety":
                self.state.metadata["website_safety_report"] = (
                    WebsiteSafetyAnalyzer.analyze(
                        self.state.metadata.get("safety_url", "")
                    )
                )
                self.state.log_reasoning("Action: Local URL safety heuristics evaluated.")

    def run(self):
        """
        Runs a simple interactive CLI for ARIA.
        """
        print("ARIA: Continuous awareness system starting...")
        while True:
            try:
                user_input = input("You: ")
                if user_input.lower() in ["exit", "quit"]:
                    break

                response = self.process_input(user_input)
                print(f"ARIA: {response}")

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")
