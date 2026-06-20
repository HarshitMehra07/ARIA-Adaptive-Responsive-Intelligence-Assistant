from memory.mission_generator import MissionGenerator


class DailyPlanner:

    @staticmethod
    def build(memories):

        mission = MissionGenerator.generate(memories)

        return {

            "morning": mission[:1],

            "afternoon": mission[1:2],

            "evening": mission[2:]

        }