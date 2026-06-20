from memory.goal_advisor import GoalAdvisor


class RecommendationEngine:

    @staticmethod
    def recommend(memories):

        report = GoalAdvisor.advise(memories)

        recommendations = []

        for skill in report["missing"]:

            recommendations.append(
                f"You should focus on {skill}"
            )

        return recommendations