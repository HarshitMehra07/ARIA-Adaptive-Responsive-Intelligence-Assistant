class FactExtractor:

    @staticmethod
    def extract_goal(text):

        lower = text.lower()

        if "become" in lower:

            parts = text.split("become")

            if len(parts) > 1:
                return parts[1].strip()

        return text

    @staticmethod
    def extract_project(text):

        lower = text.lower()

        if "project" in lower:
            return text

        return text