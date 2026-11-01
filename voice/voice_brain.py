from voice.speech_to_text import SpeechToText
from voice.text_to_speech import TextToSpeech
from voice.wake_word import WakeWord

from memory.aria_brain import ARIABrain

from memory.aria_brain import (
    ARIABrain
)


class VoiceBrain:

    @staticmethod
    def run():

        print(
            "Voice Brain Started"
        )

        while True:

            text = input(
                "You: "
            )

            if text == "exit":

                break

            result = (
                ARIABrain.process(
                    text
                )
            )

            print()

            print(
                "ARIA:",
                result[
                    "response"
                ]
            )

            print()