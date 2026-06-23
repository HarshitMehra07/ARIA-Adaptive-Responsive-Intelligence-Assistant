from vision.camera_engine import CameraEngine
from vision.face_detector import FaceDetector
from vision.emotion_detector import EmotionDetector


class VisionBrain:

    @staticmethod
    def analyze():

        CameraEngine.open()

        face_found = FaceDetector.detect()

        if face_found:

            emotion = EmotionDetector.detect()

            return {

                "face": True,

                "emotion": emotion

            }

        return {

            "face": False,

            "emotion": None

        }