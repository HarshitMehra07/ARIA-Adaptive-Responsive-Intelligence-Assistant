class TrustEngine:

    trust = {}

    @staticmethod
    def set_trust(person, score):

        TrustEngine.trust[
            person
        ] = score

    @staticmethod
    def get_trust(person):

        return TrustEngine.trust.get(
            person,
            0
        )