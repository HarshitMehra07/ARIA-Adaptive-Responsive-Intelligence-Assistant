from relationship.relationship_manager import RelationshipManager


class SocialGraph:
    """Compatibility facade for persistent, undirected relationship links."""

    @staticmethod
    def connect(person1, person2):
        return RelationshipManager.connect_people(person1, person2)

    @staticmethod
    def get_connections(person):
        return RelationshipManager.get_connections(person)
