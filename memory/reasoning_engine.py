from memory.profile_schema import UserProfile


class ReasoningEngine:

    @staticmethod
    def answer(question):

        question = question.lower()

        # Career Goal
        if "become" in question or "career" in question:

            if UserProfile.goals:

                goal = UserProfile.goals[0]

                return (
                    f"Your goal is {goal}. "
                    f"You should focus on Python, AI, ML, "
                    f"DSA, projects, and internships."
                )

        # Fitness
        if "fitness" in question or "gym" in question:

            if UserProfile.fitness:

                return (
                    "You regularly go to gym. "
                    "Focus on consistency, nutrition, "
                    "strength training, and recovery."
                )

        return "I don't have enough information yet."