from relationship.relationship_engine import (
    RelationshipEngine
)

print(
    "\n===== RELATIONSHIP =====\n"
)

RelationshipEngine.register(
    "Harshit",
    "Boss",
    100
)

RelationshipEngine.interact(
    "Harshit"
)

RelationshipEngine.interact(
    "Harshit"
)

RelationshipEngine.interact(
    "Harshit"
)

print(
    RelationshipEngine.profile(
        "Harshit"
    )
)