# ARIA browser interface

Run `python main.py --web` from the project directory. ARIA serves the browser interface at
`http://127.0.0.1:8765/` and opens it when the local server is ready. If that port is in use,
choose another local port with `python main.py --web --port 8766`.

The browser app uses the existing `AriaCore` request pipeline and its conversation, research,
document, and confirmation-gated computer-use services. The Tkinter (`python main.py` or
`python main.py --demo`) and terminal (`python main.py --cli`) launch modes remain available.
Text conversation uses the existing `POST /api/chat` route. Computer-control requests stay in
ARIA's existing policy and confirmation flow; browser chat cannot run shell or terminal commands.
Actions that submit, delete, send, publish, purchase, or otherwise commit changes require explicit
confirmation where supported, while file deletion, messaging, and purchases remain disabled.

Microphone capture starts only after the user selects **Talk to ARIA** and grants browser
permission. The interface shows when capture is active, stops after speech and a short silence,
and offers explicit stop and cancel controls. Audio is held in the tab and sent to Google's
online speech-recognition service for transcription; ARIA does not save the raw clip. Canceling
while that request is in flight stops the browser request, but cannot guarantee Google has not
already received the audio.

Voice-originated replies are automatically spoken using the existing local Windows speech
service. Choose **ARIA Voice** or **JARVIS-Style Voice Mode** for a presentation persona, then
choose an installed voice if desired. Persona changes do not change ARIA's underlying identity.
**Keep listening between responses** is an explicit opt-in; unchecking it stops capture. While
ARIA is speaking, **Interrupt and speak** stops playback before opening the microphone. Text
replies can also be played with their **Speak** control. Listening, thinking,
speaking, idle, and error states come from the backend interaction state machine. Speaking and
word-boundary animation pulses use callbacks from the local speech engine; the visualizer does
not measure speaker output amplitude. Text chat remains available if either voice service is
unavailable. The orbital animation respects the operating system's reduced-motion setting.

The optional **Enable camera** control starts local OpenCV face detection only after a click.
The interface shows when the camera is active and reports only an aggregate face count; identity
and emotion recognition are disabled. Use **Disable camera** to release it. OpenCV is included
in the requirements for this optional local capability.

**Ambient break reminders** is separately opt-in and uses only a focused-work timer. It does not
monitor the screen, microphone, or camera, and reminders appear only when the conversation is
idle. Ambient mode is disabled when the browser session closes.

The server binds exclusively to IPv4 loopback (`127.0.0.1`). The web session uses ARIA's existing
single in-process conversation state; it is not an account-based or multi-user service.
If the interface reports that the local server is out of date, stop the older ARIA server and
restart it with `python main.py --web`; the browser checks that the backend supports synchronized
voice states before enabling chat. Restarting the process clears its in-memory conversation.
