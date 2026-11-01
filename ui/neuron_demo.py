from __future__ import annotations

import math
import queue
import tkinter as tk
from tkinter import ttk

from core.aria_core import AriaCore
from voice.speech_output_service import SpeechOutputService
from voice.voice_demo_controller import VoiceDemoController, VoiceDemoState
from voice.voice_input_service import VoiceInputService


BACKGROUND = "#050b0a"
PANEL = "#0b1512"
GREEN = "#39ff9c"
EMERALD = "#0fd18b"
TEXT = "#e7fff3"
MUTED = "#91aa9e"


class NeuronCanvas(tk.Canvas):
    FRAME_MS = 33
    PARTICLE_COUNT = 26

    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            background=BACKGROUND,
            highlightthickness=0,
            **kwargs,
        )
        self.state = VoiceDemoState.IDLE
        self.reduced_motion = False
        self.speech_activity_until = 0.0
        self.phase = 0.0
        self._after_id = None
        self._closed = False
        self.bind("<Destroy>", self._on_destroy, add="+")
        self._schedule()

    def set_state(self, state: VoiceDemoState) -> None:
        self.state = state

    def set_reduced_motion(self, enabled: bool) -> None:
        self.reduced_motion = enabled

    def pulse_speech_activity(self) -> None:
        self.speech_activity_until = self.phase + 0.8

    def close(self) -> None:
        self._closed = True
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _schedule(self) -> None:
        if not self._closed and self.winfo_exists():
            self._after_id = self.after(self.FRAME_MS, self._animate)

    def _animate(self) -> None:
        self._after_id = None
        if self._closed or not self.winfo_exists():
            return
        self.phase += 0.025 if self.reduced_motion else 0.075
        self._draw_scene()
        self._schedule()

    def _draw_scene(self) -> None:
        self.delete("all")
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        cx, cy = width / 2, height / 2
        pace = 0.12 if self.reduced_motion else 1.0
        is_listening = self.state is VoiceDemoState.LISTENING
        is_thinking = self.state is VoiceDemoState.THINKING
        is_speaking = self.state is VoiceDemoState.SPEAKING
        activity = self.phase < self.speech_activity_until
        breathing = math.sin(self.phase * (0.45 if not is_listening else 0.9))
        radius = 43 + breathing * (3 if not is_listening else 5)
        if is_thinking:
            radius += 3 * math.sin(self.phase * 2.0)
        if is_speaking and activity:
            radius += 6

        ring_count = 4 if is_listening else 2
        for index in range(ring_count):
            pulse = (self.phase * pace + index / ring_count) % 1.0
            ring_radius = radius + 22 + pulse * (95 if is_listening else 58)
            color = "#0d4c37" if is_listening else "#0a3327"
            self.create_oval(
                cx - ring_radius,
                cy - ring_radius,
                cx + ring_radius,
                cy + ring_radius,
                outline=color,
                width=2 if is_listening else 1,
            )

        for index in range(8):
            angle = index * math.tau / 8 + self.phase * (0.25 if is_thinking else 0.08) * pace
            inner = radius + 7
            outer = radius + 44 + (10 * math.sin(self.phase + index) if is_thinking else 0)
            self.create_line(
                cx + math.cos(angle) * inner,
                cy + math.sin(angle) * inner,
                cx + math.cos(angle + 0.12) * outer,
                cy + math.sin(angle + 0.12) * outer,
                fill="#126c4b",
                width=2,
                smooth=True,
            )

        for index in range(self.PARTICLE_COUNT):
            angle = self.phase * pace * (0.15 + index % 4 * 0.035) + index * 2.399
            orbit = 88 + (index % 5) * 18
            x = cx + math.cos(angle) * orbit
            y = cy + math.sin(angle * (0.85 + index % 3 * 0.07)) * orbit * 0.63
            size = 2.5 if index % 4 else 3.5
            color = GREEN if (is_speaking and activity and index % 3 == 0) else EMERALD
            self.create_oval(
                x - size,
                y - size,
                x + size,
                y + size,
                fill=color,
                outline="",
            )

        for index, color in enumerate(("#0b4a34", "#0c714b", "#139b63", GREEN)):
            glow = radius + (12 - index * 3)
            self.create_oval(
                cx - glow,
                cy - glow,
                cx + glow,
                cy + glow,
                fill=color,
                outline="",
            )
        self.create_oval(
            cx - radius,
            cy - radius,
            cx + radius,
            cy + radius,
            fill="#0c3023",
            outline="#70ffc0",
            width=2,
        )
        self.create_oval(
            cx - radius * 0.53,
            cy - radius * 0.53,
            cx + radius * 0.53,
            cy + radius * 0.53,
            fill="#c0ffe0",
            outline="",
        )
        label = {
            VoiceDemoState.IDLE: "READY",
            VoiceDemoState.LISTENING: "LISTENING",
            VoiceDemoState.THINKING: "PROCESSING",
            VoiceDemoState.SPEAKING: "SPEAKING",
        }[self.state]
        self.create_text(
            cx,
            cy + 112,
            text=label,
            fill=GREEN,
            font=("Segoe UI", 10, "bold"),
        )

    def _on_destroy(self, event) -> None:
        if event.widget is self:
            self.close()


class TeacherDemoApp:
    def __init__(self, root: tk.Tk, *, aria=None, voice_input=None, speech_output=None):
        self.root = root
        self.aria = aria if aria is not None else AriaCore()
        self.voice_input = voice_input if voice_input is not None else VoiceInputService()
        self.speech_output = speech_output if speech_output is not None else SpeechOutputService()
        self._closing = False
        self._ui_callbacks = queue.Queue()
        self._ui_poll_id = None
        self._voice_ids: dict[str, str] = {}
        self.state_var = tk.StringVar(value=VoiceDemoState.IDLE.value)
        self.status_var = tk.StringVar(value="Starting local speech output...")
        if VoiceInputService.dependencies_available():
            voice_status = (
                "Voice input dependencies are installed. Microphone access is checked only when you start listening."
            )
        else:
            voice_status = (
                "Voice input unavailable: install the voice dependencies. Text requests remain available."
            )
        self.voice_services_var = tk.StringVar(value=voice_status)
        self.voice_var = tk.StringVar(value="System default")
        self.persona_var = tk.StringVar(value="ARIA Voice")
        self.continuous_var = tk.BooleanVar(value=False)
        self.reduced_motion_var = tk.BooleanVar(value=False)

        self._configure_window()
        self._build_ui()
        self._schedule_ui_poll()
        self.controller = VoiceDemoController(
            self.aria,
            self.voice_input,
            self.speech_output,
            dispatch=self._dispatch,
            on_state=self._on_state,
            on_transcript=self._on_transcript,
            on_response=self._on_response,
            on_status=self._on_status,
            on_error=self._on_error,
            on_speech_activity=self.neuron.pulse_speech_activity,
        )
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.speech_output.start(
            on_ready=lambda voices: self._dispatch(lambda: self._on_voices_ready(voices)),
            on_error=lambda message: self._dispatch(lambda: self._on_tts_unavailable(message)),
        )
        self._refresh_controls()

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        if self._ui_poll_id is not None:
            try:
                self.root.after_cancel(self._ui_poll_id)
            except tk.TclError:
                pass
            self._ui_poll_id = None
        self.controller.close()
        self.neuron.close()
        self.root.destroy()

    def _configure_window(self) -> None:
        self.root.title("ARIA | Voice Demonstration")
        self.root.geometry("940x900")
        self.root.minsize(760, 760)
        self.root.configure(background=BACKGROUND)
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            ".",
            background=BACKGROUND,
            foreground=TEXT,
            fieldbackground=PANEL,
            font=("Segoe UI", 10),
        )
        style.configure("TFrame", background=BACKGROUND)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BACKGROUND, foreground=TEXT)
        style.configure("Muted.TLabel", background=BACKGROUND, foreground=MUTED)
        style.configure("Title.TLabel", background=BACKGROUND, foreground=GREEN, font=("Segoe UI", 23, "bold"))
        style.configure("State.TLabel", background=BACKGROUND, foreground=GREEN, font=("Segoe UI", 11, "bold"))
        style.configure("TButton", padding=(14, 9), background="#103a2b", foreground=TEXT)
        style.map("TButton", background=[("active", "#176444"), ("disabled", "#18241f")])
        style.configure("Accent.TButton", background="#08784d", foreground="#ffffff", font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#10a765")])
        style.configure("TEntry", padding=10, insertcolor=GREEN)
        style.configure("TCombobox", padding=6)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=(28, 22))
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x")
        ttk.Label(header, text="ARIA", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="VOICE INTERFACE  /  LIVE DEMO", style="Muted.TLabel").pack(
            side="left", padx=(14, 0), pady=(9, 0)
        )
        self.state_label = ttk.Label(header, textvariable=self.state_var, style="State.TLabel")
        self.state_label.pack(side="right", pady=(8, 0))

        ttk.Label(
            outer,
            text="A personal assistant, ready to listen.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(2, 8))

        self.neuron = NeuronCanvas(outer, height=335)
        self.neuron.pack(fill="x", expand=False, pady=(0, 8))

        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=(0, 12))
        self.mic_button = ttk.Button(
            controls,
            text="Start listening",
            style="Accent.TButton",
            command=self._toggle_listening,
        )
        self.mic_button.pack(side="left")
        self.stop_button = ttk.Button(
            controls,
            text="Stop speaking",
            command=self.controller_stop_speech,
        )
        self.stop_button.pack(side="left", padx=(10, 0))
        ttk.Label(controls, text="Voice", style="Muted.TLabel").pack(side="left", padx=(22, 7))
        self.voice_picker = ttk.Combobox(
            controls,
            textvariable=self.voice_var,
            state="readonly",
            width=27,
            values=("System default",),
        )
        self.voice_picker.pack(side="left")
        self.voice_picker.bind("<<ComboboxSelected>>", self._select_voice)
        ttk.Label(controls, text="Identity", style="Muted.TLabel").pack(
            side="left", padx=(12, 7)
        )
        self.persona_picker = ttk.Combobox(
            controls,
            textvariable=self.persona_var,
            state="readonly",
            width=22,
            values=("ARIA Voice", "JARVIS-Style Voice"),
        )
        self.persona_picker.pack(side="left")
        self.persona_picker.bind("<<ComboboxSelected>>", self._select_persona)
        self.continuous_check = ttk.Checkbutton(
            outer,
            text="Keep listening between responses (microphone remains opt-in)",
            variable=self.continuous_var,
            command=self._toggle_continuous,
        )
        self.continuous_check.pack(anchor="w", pady=(0, 10))
        self.motion_check = ttk.Checkbutton(
            controls,
            text="Reduced motion",
            variable=self.reduced_motion_var,
            command=lambda: self.neuron.set_reduced_motion(self.reduced_motion_var.get()),
        )
        self.motion_check.pack(side="right")

        self.status_label = ttk.Label(
            outer,
            textvariable=self.status_var,
            style="Muted.TLabel",
            wraplength=860,
        )
        self.status_label.pack(fill="x", anchor="w", pady=(0, 12))
        ttk.Label(
            outer,
            text="Microphone privacy",
            foreground=GREEN,
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text=(
                "Voice recognition uses Google's online service: audio is sent for transcription and is not saved by ARIA. "
                "The microphone opens only when you click Start listening. Type instead to keep audio off."
            ),
            style="Muted.TLabel",
            wraplength=860,
            justify="left",
        ).pack(fill="x", anchor="w", pady=(2, 12))
        ttk.Label(
            outer,
            textvariable=self.voice_services_var,
            style="Muted.TLabel",
            wraplength=860,
        ).pack(fill="x", anchor="w", pady=(0, 10))

        self.transcript_var = tk.StringVar(value="Your recognized speech or typed request will appear here.")
        self.response_var = tk.StringVar(value="ARIA's response will appear here.")
        self._build_text_panel(outer, "YOU", self.transcript_var, height=3)
        self._build_text_panel(outer, "ARIA", self.response_var, height=5)

        input_row = ttk.Frame(outer)
        input_row.pack(fill="x", pady=(12, 0))
        self.request_var = tk.StringVar()
        self.request_entry = ttk.Entry(input_row, textvariable=self.request_var)
        self.request_entry.pack(side="left", fill="x", expand=True)
        self.request_entry.bind("<Return>", self._send_text)
        self.send_button = ttk.Button(
            input_row,
            text="Send",
            style="Accent.TButton",
            command=self._send_text,
        )
        self.send_button.pack(side="left", padx=(10, 0))

    def _build_text_panel(self, parent, title, variable, *, height: int) -> None:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=(14, 10))
        panel.pack(fill="x", pady=5)
        ttk.Label(panel, text=title, foreground=GREEN).pack(anchor="w")
        ttk.Label(
            panel,
            textvariable=variable,
            wraplength=850,
            justify="left",
            background=PANEL,
            foreground=TEXT,
        ).pack(fill="x", anchor="w", pady=(4, 0))

    def _dispatch(self, callback) -> None:
        if self._closing:
            return
        self._ui_callbacks.put(callback)

    def _schedule_ui_poll(self) -> None:
        if not self._closing:
            self._ui_poll_id = self.root.after(25, self._drain_ui_callbacks)

    def _drain_ui_callbacks(self) -> None:
        self._ui_poll_id = None
        if self._closing:
            return
        while True:
            try:
                callback = self._ui_callbacks.get_nowait()
            except queue.Empty:
                break
            callback()
        self._schedule_ui_poll()

    def _toggle_listening(self) -> None:
        if self.controller.state is VoiceDemoState.LISTENING:
            self.status_var.set("Stopping microphone capture...")
            self.continuous_var.set(False)
            self.controller.cancel_listening()
        elif self.controller.state is VoiceDemoState.SPEAKING:
            self.status_var.set("Interrupting speech and opening the microphone...")
            self.controller.start_listening()
        else:
            self.status_var.set(
                "Listening once. Audio will be sent to Google's online transcription service."
            )
            self.controller.start_listening()
        self._refresh_controls()

    def _toggle_continuous(self) -> None:
        enabled = self.continuous_var.get()
        if not self.controller.set_continuous(enabled):
            self.continuous_var.set(False)
            self.status_var.set("Continuous listening could not be started in the current state.")
        elif enabled:
            self.status_var.set("Continuous listening is on. The microphone is active between turns.")
        else:
            self.status_var.set("Continuous listening is off.")
        self._refresh_controls()

    def _send_text(self, _event=None) -> None:
        text = self.request_var.get()
        if self.controller.submit_text(text):
            self.request_var.set("")
            self.status_var.set("ARIA is thinking...")
        self._refresh_controls()

    def controller_stop_speech(self) -> None:
        if self.controller.stop_speaking():
            self.status_var.set("Stopping speech playback...")

    def _on_state(self, state: VoiceDemoState) -> None:
        if self._closing:
            return
        self.state_var.set(state.value)
        self.neuron.set_state(state)
        self._refresh_controls()
        if state is VoiceDemoState.IDLE and self.status_var.get() in {
            "ARIA is thinking...",
            "Stopping speech playback...",
            "Stopping microphone capture...",
        }:
            self.status_var.set("Ready. Type a request or click Start listening.")

    def _on_transcript(self, text: str) -> None:
        self.transcript_var.set(text)
        self.status_var.set("Request recognized. ARIA is thinking...")

    def _on_response(self, text: str) -> None:
        self.response_var.set(text)
        self.status_var.set("Response ready. Starting local speech playback...")

    def _on_status(self, message: str) -> None:
        self.status_var.set(message)

    def _on_error(self, message: str) -> None:
        self.continuous_var.set(False)
        self.status_var.set(message)

    def _on_tts_unavailable(self, message: str) -> None:
        self.status_var.set(message)
        self.voice_services_var.set(
            "Local speech output unavailable. ARIA responses remain visible; text requests remain available."
        )

    def _on_voices_ready(self, voices) -> None:
        values = ["System default"]
        for voice in voices:
            display = voice.name[:80]
            if display in self._voice_ids:
                display = f"{display} ({len(self._voice_ids) + 1})"
            self._voice_ids[display] = voice.voice_id
            values.append(display)
        self.voice_picker.configure(values=tuple(values))
        self.controller.set_voice_persona("aria")
        selected_voice = self.speech_output.selected_voice_id
        self.voice_var.set(
            next(
                (name for name, voice_id in self._voice_ids.items() if voice_id == selected_voice),
                "System default",
            )
        )
        self.status_var.set("Local speech output is ready. Voice input is opt-in.")
        if VoiceInputService.dependencies_available():
            self.voice_services_var.set(
                "Online voice input dependencies installed; microphone availability is checked on activation."
            )

    def _select_voice(self, _event=None) -> None:
        selection = self.voice_var.get()
        voice_id = self._voice_ids.get(selection)
        if not self.speech_output.select_voice(voice_id):
            self.status_var.set("That system voice could not be selected.")

    def _select_persona(self, _event=None) -> None:
        persona = "jarvis" if self.persona_var.get() == "JARVIS-Style Voice" else "aria"
        if not self.controller.set_voice_persona(persona):
            self.status_var.set("That voice identity could not be selected.")
            return
        selected_voice = self.speech_output.selected_voice_id
        self.voice_var.set(
            next(
                (name for name, voice_id in self._voice_ids.items() if voice_id == selected_voice),
                "System default",
            )
        )

    def _refresh_controls(self) -> None:
        state = self.controller.state if hasattr(self, "controller") else VoiceDemoState.IDLE
        self.mic_button.configure(
            text=(
                "Stop listening"
                if state is VoiceDemoState.LISTENING
                else "Interrupt and listen"
                if state is VoiceDemoState.SPEAKING
                else "Start listening"
            ),
            state=(
                "normal"
                if state
                in {
                    VoiceDemoState.IDLE,
                    VoiceDemoState.LISTENING,
                    VoiceDemoState.SPEAKING,
                }
                else "disabled"
            ),
        )
        self.send_button.configure(state="normal" if state is VoiceDemoState.IDLE else "disabled")
        self.request_entry.configure(state="normal" if state is VoiceDemoState.IDLE else "disabled")
        self.stop_button.configure(state="normal" if state is VoiceDemoState.SPEAKING else "disabled")
        self.continuous_check.configure(
            state="normal"
            if state
            in {
                VoiceDemoState.IDLE,
                VoiceDemoState.LISTENING,
                VoiceDemoState.SPEAKING,
            }
            else "disabled"
        )


def launch_demo() -> None:
    root = tk.Tk()
    TeacherDemoApp(root)
    root.mainloop()


if __name__ == "__main__":
    launch_demo()
