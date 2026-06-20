# memory/profile_manager.py

from memory.profile_schema import UserProfile


class ProfileManager:

    @staticmethod
    def show_profile():

        print("\n===== USER PROFILE =====")

        print("Goals:", UserProfile.goals)

        print("Projects:", UserProfile.projects)

        print("Fitness:", UserProfile.fitness)

        print("Education:", UserProfile.education)

        print("Career:", UserProfile.career)