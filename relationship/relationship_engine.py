from relationship.nickname_engine import (
    NicknameEngine
)

from relationship.trust_engine import (
    TrustEngine
)

from relationship.bond_engine import (
    BondEngine
)


class RelationshipEngine:

    @staticmethod
    def register(
        person,
        nickname,
        trust
    ):

        NicknameEngine.set_name(
            person,
            nickname
        )

        TrustEngine.set_trust(
            person,
            trust
        )

    @staticmethod
    def interact(person):

        BondEngine.interact(
            person
        )

    @staticmethod
    def profile(person):

        return {

            "name":
            NicknameEngine.get_name(
                person
            ),

            "trust":
            TrustEngine.get_trust(
                person
            ),

            "bond":
            BondEngine.get_bond(
                person
            )
        }