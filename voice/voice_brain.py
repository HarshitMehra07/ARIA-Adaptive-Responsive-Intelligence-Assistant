from voice.speech_to_text import SpeechToText
from voice.text_to_speech import TextToSpeech
from voice.wake_word import WakeWord

from memory.aria_brain import ARIABrain


class VoiceBrain:

    @staticmethod
    def run():

        print(
            "\nVoice Brain Started"
        )

        while True:

            text = SpeechToText.listen()

            if text.lower() == "exit":

                print("Stopping")

                break

            if WakeWord.detect(text):

                result = ARIABrain.process(text)

                response = result["response"]

                TextToSpeech.speak(
                    response
                )