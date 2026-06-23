from memory.user_rules_engine import UserRulesEngine

UserRulesEngine.set_rule(
    "title",
    "Boss"
)

print(
    UserRulesEngine.get_rule(
        "title"
    )
)