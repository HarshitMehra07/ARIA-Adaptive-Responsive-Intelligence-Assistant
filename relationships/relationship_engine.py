from relationship.relationship_manager import RelationshipManager


class RelationshipEngine:
    """Compatibility facade for the unified persistent relationship profiles."""

    @staticmethod
    def add(person, relation):
        return RelationshipManager.set_relationship(person, relation)

    @staticmethod
    def get(person):
        profile = RelationshipManager.get_person(person)
        return profile["relationship_type"] if profile else "Unknown"
