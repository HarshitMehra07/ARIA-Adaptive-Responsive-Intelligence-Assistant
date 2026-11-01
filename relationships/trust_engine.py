from relationship.relationship_manager import RelationshipManager


class TrustEngine:
    """Compatibility facade for trust scores stored in relationship profiles."""

    @staticmethod
    def update(person, score):
        return RelationshipManager.save_person(
            person,
            trust_level=max(0, min(int(score), 100)),
        )

    @staticmethod
    def get(person):
        profile = RelationshipManager.get_person(person)
        return profile["trust_level"] if profile else 0
