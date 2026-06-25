class BondEngine:

    bonds = {}

    @staticmethod
    def interact(person):

        BondEngine.bonds[
            person
        ] = BondEngine.bonds.get(
            person,
            0
        ) + 1

    @staticmethod
    def get_bond(person):

        return BondEngine.bonds.get(
            person,
            0
        )