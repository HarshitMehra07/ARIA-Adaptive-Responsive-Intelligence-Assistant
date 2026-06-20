# memory/profile_builder.py

from memory.profile_schema import UserProfile
from memory.fact_extractor import FactExtractor

class ProfileBuilder:

    @staticmethod
    def update_profile(text):

        lower = text.lower()

        if "goal" in lower:

            goal = FactExtractor.extract_goal(text)
            UserProfile.goals.append(goal)

            if "project" in lower:
                UserProfile.projects.append(text)

            if "gym" in lower:
                UserProfile.fitness.append(text)

            if "college" in lower:
                UserProfile.education.append(text)

            if "engineer" in lower:
                UserProfile.career.append(text)