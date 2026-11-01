# ARIA voice demonstration

The demo uses the existing ARIA request pipeline and a standard-library Tkinter
window. It does not record continuously. Clicking **Start listening** captures
one bounded utterance in memory, then sends it to Google's online speech
recognition service. ARIA does not save the raw recording; use text input if you
do not want audio sent online. An internet connection is required for voice
recognition.

Speech playback uses `pyttsx3` with the locally installed Windows SAPI voice.
Playback remains local. The neuron animation is capped at about 30 frames per
second. Its speaking pulse follows the TTS engine's word-start events; it is an
activity indicator, not a measured audio waveform.

Choose **ARIA Voice** or **JARVIS-Style Voice** to change speech presentation
without changing ARIA's underlying identity. **Keep listening between responses**
is off by default and can be disabled at any time. While ARIA is speaking, use
**Interrupt and listen** to stop playback and start a microphone turn.

## Setup and launch (PowerShell)

From the project root:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe main.py
```

If using a different Python environment, install the same requirements into it
and run `python main.py`. Use `python main.py --cli` to launch the terminal
interface. The `--demo` option is retained as an explicit alias for the
desktop interface. Before using the microphone, allow microphone
access for desktop apps in **Windows Settings > Privacy & security > Microphone**.
The demo reports a microphone, network, or local speech-output problem and
keeps text requests available.
