class UserRulesEngine:

    rules = {}

    @staticmethod
    def set_rule(key, value):

        UserRulesEngine.rules[key] = value

    @staticmethod
    def get_rule(key):

        return UserRulesEngine.rules.get(
            key
        )