from relationships.people_memory import (
    PeopleMemory
)

from relationships.relationship_engine import (
    RelationshipEngine
)

from relationships.social_graph import (
    SocialGraph
)

from relationships.trust_engine import (
    TrustEngine
)

print(
    "\n===== RELATIONSHIP TEST =====\n"
)

RelationshipEngine.add(
    "Mom",
    "Mother"
)

PeopleMemory.remember(
    "Mom",
    "Likes Tea"
)

SocialGraph.connect(
    "Harshit",
    "Mom"
)

TrustEngine.update(
    "Mom",
    100
)

print(
    RelationshipEngine.get("Mom")
)

print(
    PeopleMemory.recall("Mom")
)

print(
    SocialGraph.get_connections(
        "Harshit"
    )
)

print(
    TrustEngine.get("Mom")
)