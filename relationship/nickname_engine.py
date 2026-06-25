class NicknameEngine:

    nicknames = {}

    @staticmethod
    def set_name(person, nickname):

        NicknameEngine.nicknames[
            person
        ] = nickname

    @staticmethod
    def get_name(person):

        return NicknameEngine.nicknames.get(
            person,
            person
        )