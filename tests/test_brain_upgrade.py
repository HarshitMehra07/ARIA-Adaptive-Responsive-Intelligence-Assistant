from core.conversation_manager import ConversationManager
from core.context_manager import ContextManager
from core.knowledge_engine import KnowledgeEngine


print("\n===== ARIA BRAIN UPGRADE =====\n")


# --------------------------------
# TEST 1
# Conversation context
# --------------------------------

ConversationManager.clear()

text1 = "My goal is AI Engineer"

ConversationManager.add_user_message(
    text1
)

resolved1 = ContextManager.resolve(
    text1
)

print("INPUT 1:")
print(text1)

print("\nRESOLVED 1:")
print(resolved1)


# --------------------------------
# TEST 2
# Follow-up understanding
# --------------------------------

text2 = "How can I achieve it"

ConversationManager.add_user_message(
    text2
)

resolved2 = ContextManager.resolve(
    text2
)

print("\nINPUT 2:")
print(text2)

print("\nRESOLVED 2:")
print(resolved2)


# --------------------------------
# TEST 3
# Current goal
# --------------------------------

print("\nCURRENT GOAL:")

print(
    ConversationManager.get_goal()
)


# --------------------------------
# TEST 4
# Conversation history
# --------------------------------

print("\nCONVERSATION HISTORY:")

for message in ConversationManager.get_history():

    print(
        message["role"],
        ":",
        message["content"]
    )


# --------------------------------
# TEST 5
# Knowledge
# --------------------------------

KnowledgeEngine.learn(
    "preferred title",
    "Boss",
    source="user"
)

KnowledgeEngine.learn(
    "career goal",
    "AI Engineer",
    source="user"
)

print("\nKNOWLEDGE:")

print(
    KnowledgeEngine.get_all()
)


print("\nSEARCH:")

print(
    KnowledgeEngine.search(
        "career goal"
    )
)


print("\n===== TEST COMPLETE =====")