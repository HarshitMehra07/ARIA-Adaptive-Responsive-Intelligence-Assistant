from relationship.relationship_manager import RelationshipManager


class RelationshipEngine:
    """Compatibility facade over the persistent relationship profile manager."""

    @staticmethod
    def register(person, nickname=None, trust=50):
        return RelationshipManager.save_person(
            person,
            nickname=nickname,
            trust_level=trust,
        )

    @staticmethod
    def interact(person):
        return RelationshipManager.record_interaction(person)

    @staticmethod
    def profile(person):
        profile = RelationshipManager.get_person(person)
        if not profile:
            return {
                "name": person,
                "nickname": person,
                "trust": 0,
                "bond": 0,
            }
        return {
            "name": profile["name"],
            "nickname": profile["nickname"] or profile["name"],
            "trust": profile["trust_level"],
            "bond": profile["bond_score"],
        }
