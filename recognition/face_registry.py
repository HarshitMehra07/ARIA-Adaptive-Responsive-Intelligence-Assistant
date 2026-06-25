class FaceRegistry:

    faces = {}

    @staticmethod
    def register(
        face_id,
        person
    ):

        FaceRegistry.faces[
            face_id
        ] = person

    @staticmethod
    def identify(face_id):

        return FaceRegistry.faces.get(
            face_id,
            None
        )