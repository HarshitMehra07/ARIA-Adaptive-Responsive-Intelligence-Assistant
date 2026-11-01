"use strict";

const elements = {
  connection: document.querySelector("#connection"),
  connectionText: document.querySelector("#connection-text"),
  stage: document.querySelector("#neuron-stage"),
  nucleusAura: document.querySelector(".nucleus-aura"),
  nucleus: document.querySelector(".nucleus"),
  atomModel: document.querySelector(".atom-model"),
  state: document.querySelector("#aria-state"),
  stateMode: document.querySelector("#state-mode"),
  messages: document.querySelector("#messages"),
  welcome: document.querySelector("#welcome-message"),
  form: document.querySelector("#chat-form"),
  input: document.querySelector("#chat-input"),
  send: document.querySelector("#send-button"),
  error: document.querySelector("#error-banner"),
  mic: document.querySelector("#mic-button"),
  voiceStatus: document.querySelector("#voice-status"),
  voicePersona: document.querySelector("#voice-persona"),
  voiceGender: document.querySelector("#voice-gender"),
  voiceSelect: document.querySelector("#voice-select"),
  stopSpeech: document.querySelector("#stop-speech"),
  recordingActions: document.querySelector("#recording-actions"),
  finishRecording: document.querySelector("#finish-recording"),
  cancelRecording: document.querySelector("#cancel-recording"),
  continuousListening: document.querySelector("#continuous-listening"),
  visionButton: document.querySelector("#vision-button"),
  visionStatus: document.querySelector("#vision-status"),
  ambientMode: document.querySelector("#ambient-mode"),
  toast: document.querySelector("#toast"),
};

const stateLabels = {
  idle: ["Ready when you are", "IDLE", "ARIA is ready"],
  listening: ["Listening to your voice", "LISTENING", "ARIA is listening"],
  thinking: ["Thinking through your request", "THINKING", "ARIA is thinking"],
  speaking: ["ARIA is speaking", "SPEAKING", "ARIA is speaking"],
  error: ["Voice request needs attention", "ERROR", "ARIA encountered an error"],
};
const staleServerMessage =
  "ARIA's local server is out of date. Stop the old server and restart with `python main.py --web`.";

let connected = false;
let sending = false;
let recording = null;
let speechPoll = null;
let toastTimer = null;
let statusTimer = null;
let speechPulseTimer = null;
let transcriptionAvailable = false;
let lastSpeechEventId = 0;
let lastObservedSpeechState = "idle";
let lastInteractionEventId = -1;
let voiceOptionsKey = "";
let speechStarted = false;
let speechPending = false;
let interactionId = null;
let voiceStatusRequestInFlight = false;
let continuousStartTimer = null;
let visionPoll = null;
let ambientPoll = null;
let visionActive = false;
let ambientEnabled = false;
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

function configureOrbitSpeed(state) {
  const durations = {
    idle: ["18s", "14s", "11s"],
    listening: ["11s", "8s", "6s"],
    thinking: ["8s", "6s", "5s"],
    speaking: ["9s", "6s", "4s"],
    error: ["24s", "20s", "18s"],
  };
  const speed = reducedMotion.matches ? ["36s", "30s", "24s"] : durations[state] || durations.idle;
  document.querySelectorAll(".orbital animateMotion").forEach((motion, index) => {
    motion.setAttribute("dur", speed[index]);
  });
  if (reducedMotion.matches) elements.atomModel.pauseAnimations();
  else elements.atomModel.unpauseAnimations();
}
reducedMotion.addEventListener("change", () => configureOrbitSpeed(elements.stage.dataset.state));

function setState(name) {
  const [label, mode, description] = stateLabels[name] || stateLabels.idle;
  elements.stage.dataset.state = name;
  elements.stage.setAttribute("aria-label", description);
  elements.state.textContent = label;
  elements.stateMode.textContent = mode;
  configureOrbitSpeed(name);
  updateControls();
}

function updateControls() {
  const state = elements.stage.dataset.state;
  const active = ["listening", "thinking", "speaking"].includes(state);
  elements.send.disabled = !connected || sending || Boolean(recording) || !elements.input.value.trim();
  elements.mic.disabled = !connected || sending || Boolean(recording)
    || (active && state !== "speaking")
    || !transcriptionAvailable;
  elements.mic.querySelector("span").textContent = state === "speaking"
    ? "Interrupt and speak"
    : "Talk to ARIA";
  elements.mic.setAttribute(
    "aria-label",
    state === "speaking" ? "Interrupt ARIA and start speaking" : "Start microphone recording",
  );
}

function scheduleContinuousListening() {
  if (
    !elements.continuousListening.checked
    || !connected
    || recording
    || !["idle", "error"].includes(elements.stage.dataset.state)
  ) return;
  window.clearTimeout(continuousStartTimer);
  continuousStartTimer = window.setTimeout(() => {
    continuousStartTimer = null;
    if (elements.continuousListening.checked) void beginRecording();
  }, 350);
}

function startInteractionPolling() {
  if (!speechPoll) speechPoll = window.setInterval(updateVoiceStatus, 200);
}

async function changeInteractionState(state, id = interactionId, error = null) {
  const sessionId = id || crypto.randomUUID();
  const result = await api("/api/voice/interaction", {
    method: "POST",
    body: JSON.stringify({ interaction_id: sessionId, state, error }),
  });
  interactionId = ["idle", "error"].includes(state) ? null : sessionId;
  applyInteractionState(result.state, result.event_id);
  if (interactionId) startInteractionPolling();
  return result;
}

function applyInteractionState(state, eventId) {
  if (!Number.isInteger(eventId) || eventId < lastInteractionEventId) return;
  lastInteractionEventId = eventId;
  setState(state);
}

function setConnection(isConnected) {
  connected = isConnected;
  elements.connection.classList.toggle("connected", isConnected);
  elements.connection.classList.toggle("disconnected", !isConnected);
  elements.connectionText.textContent = isConnected ? "Connected" : "Offline";
  updateControls();
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: { ...(options.body instanceof Blob ? {} : { "Content-Type": "application/json" }), ...options.headers },
  });
  let payload;
  try {
    payload = await response.json();
  } catch (error) {
    console.error("[ARIA ERROR] API response was not valid JSON", { url, status: response.status, error });
    payload = {};
  }
  if (!response.ok) {
    if (response.status === 404 && url === "/api/voice/interaction") {
      throw new Error(staleServerMessage);
    }
    throw new Error(typeof payload.detail === "string" ? payload.detail : `Request failed (${response.status}).`);
  }
  return payload;
}

function hideWelcome() {
  if (elements.welcome) {
    elements.welcome.remove();
    elements.welcome = null;
  }
}

function appendMessage(role, text, { speak = role === "assistant" } = {}) {
  hideWelcome();
  const wrapper = document.createElement("article");
  wrapper.className = `message ${role === "user" ? "user" : "assistant"}`;

  const metadata = document.createElement("div");
  metadata.className = "message-meta";
  const badge = document.createElement("span");
  badge.className = "message-badge";
  badge.textContent = role === "user" ? "Y" : "A";
  const name = document.createElement("span");
  name.textContent = role === "user" ? "YOU" : "ARIA";
  metadata.append(badge, name);

  const body = document.createElement("div");
  body.className = "message-body";
  body.textContent = text;
  wrapper.append(metadata, body);

  if (speak && role === "assistant") {
    const tools = document.createElement("div");
    tools.className = "message-tools";
    const speakButton = document.createElement("button");
    speakButton.className = "message-tool";
    speakButton.type = "button";
    speakButton.textContent = "▶ Speak";
    speakButton.setAttribute("aria-label", "Speak this ARIA reply");
    speakButton.addEventListener("click", () => speakReply(text));
    tools.append(speakButton);
    wrapper.append(tools);
  }

  elements.messages.append(wrapper);
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

function showTyping() {
  hideWelcome();
  const typing = document.createElement("div");
  typing.className = "typing";
  typing.id = "typing-indicator";
  typing.setAttribute("aria-label", "ARIA is thinking");
  for (let index = 0; index < 3; index += 1) {
    typing.append(document.createElement("span"));
  }
  elements.messages.append(typing);
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

function removeTyping() {
  document.querySelector("#typing-indicator")?.remove();
}

function showError(message) {
  elements.error.textContent = message;
  elements.error.hidden = false;
}

function clearError() {
  elements.error.hidden = true;
  elements.error.textContent = "";
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add("show");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => elements.toast.classList.remove("show"), 2800);
}

async function loadHistory() {
  try {
    const { messages } = await api("/api/history");
    if (Array.isArray(messages) && messages.length) {
      hideWelcome();
      for (const message of messages) {
        if (message && (message.role === "user" || message.role === "assistant") && typeof message.content === "string") {
          appendMessage(message.role, message.content);
        }
      }
    }
  } catch (error) {
    showError(error.message);
  }
}

async function processUserInput(text, source = "text", { voiceInteractionId = null } = {}) {
  const message = typeof text === "string" ? text.trim() : "";
  if (!message) {
    showError("Enter a message before sending.");
    return { completed: false, speechAccepted: false };
  }
  if (!["text", "voice"].includes(source)) {
    showError("This message source is not supported.");
    return { completed: false, speechAccepted: false };
  }
  if (sending || recording || !connected) {
    showError("ARIA is not ready to accept another message yet.");
    return { completed: false, speechAccepted: false };
  }
  if (source === "voice" && !voiceInteractionId) {
    showError("The voice interaction expired. Start a new recording and try again.");
    return { completed: false, speechAccepted: false };
  }
  clearError();
  sending = true;
  const currentInteractionId = source === "voice" ? voiceInteractionId : null;
  console.info("[ARIA INPUT] User message received", { source, characters: message.length });
  updateControls();
  try {
    appendMessage("user", message, { speak: false });
    console.info("[ARIA UI] User message added to chat");
    if (source === "text") {
      elements.input.value = "";
      resizeInput();
      setState("thinking");
    }
    if (source === "voice") {
      interactionId = voiceInteractionId;
    }
    if (speechStarted || speechPending) {
      try {
        await api("/api/voice/stop", { method: "POST" });
      } catch (error) {
        console.error("[ARIA ERROR] Previous speech could not be interrupted", error);
        elements.voiceStatus.textContent = "The previous speech could not be interrupted; the text request will continue.";
      }
      speechStarted = false;
      speechPending = false;
    }
    showTyping();
    console.info("[ARIA BRAIN] Processing request", { source });
    const response = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        text: message,
        source,
        ...(currentInteractionId ? { interaction_id: currentInteractionId } : {}),
      }),
    });
    if (typeof response.response !== "string" || !response.response.trim()) {
      throw new Error("ARIA returned an empty response.");
    }
    removeTyping();
    console.info("[ARIA RESPONSE] Response generated", { characters: response.response.trim().length });
    appendMessage("assistant", response.response);
    console.info("[ARIA UI] ARIA response added to chat");
    const speechAccepted = source === "voice"
      ? await speakReply(response.response, currentInteractionId)
      : null;
    if (source === "text") {
      setState("idle");
      elements.voiceStatus.textContent = transcriptionAvailable
        ? "Text response ready. Voice is available whenever you need it."
        : "Text response ready. Voice recognition is unavailable.";
    }
    return { completed: true, speechAccepted };
  } catch (error) {
    console.error("[ARIA ERROR] Message processing failed", error);
    removeTyping();
    showError(error.message || "ARIA couldn't process this message.");
    if (source === "voice") {
      try {
        await changeInteractionState("error", currentInteractionId, error.message);
      } catch (stateError) {
        console.error("[ARIA ERROR] Voice interaction state recovery failed", stateError);
        setState("error");
      }
    } else {
      setState("idle");
    }
    return { completed: false, speechAccepted: false };
  } finally {
    sending = false;
    if (source === "text" && elements.stage.dataset.state === "thinking") {
      setState("idle");
    }
    updateControls();
  }
}

async function checkHealth() {
  try {
    const health = await api("/api/health");
    if (health.voice_state_api !== 1) {
      throw new Error(staleServerMessage);
    }
    setConnection(true);
    if (elements.error.textContent.includes("local server is out of date")) clearError();
  } catch (error) {
    setConnection(false);
    lastInteractionEventId = -1;
    lastSpeechEventId = 0;
    setState("idle");
    const message = error.message?.includes("local server is out of date")
      ? error.message
      : "ARIA's local server is unavailable. Check the server window and try again.";
    elements.voiceStatus.textContent = message;
    showError(message);
  }
}

async function updateVoiceStatus() {
  if (voiceStatusRequestInFlight) return;
  voiceStatusRequestInFlight = true;
  try {
    const status = await api("/api/voice/status");
    if (
      typeof status.interaction_state !== "string"
      || !Number.isInteger(status.interaction_event_id)
    ) {
      throw new Error(staleServerMessage);
    }
    const ownsInteraction = Boolean(
      interactionId && interactionId === status.interaction_session_id,
    );
    if (
      !recording
      && !sending
      && !ownsInteraction
      && ["listening", "thinking"].includes(status.interaction_state)
      && typeof status.interaction_session_id === "string"
    ) {
      console.warn("[ARIA VOICE] Recovering an unowned interaction.");
      await changeInteractionState("idle", status.interaction_session_id);
      return;
    }
    transcriptionAvailable = status.transcription_available === true;
    if (status.voice_persona === "aria" || status.voice_persona === "jarvis") {
      elements.voicePersona.value = status.voice_persona;
    }
    const stateIsCurrent = status.interaction_event_id >= lastInteractionEventId;
    if (stateIsCurrent && (!sending || ownsInteraction)) {
      applyInteractionState(status.interaction_state, status.interaction_event_id);
    }
    if (
      stateIsCurrent
      && (status.interaction_state === "idle" || status.interaction_state === "error")
    ) {
      interactionId = null;
      if (speechPoll) {
        window.clearInterval(speechPoll);
        speechPoll = null;
      }
    }
    updateControls();
    if (recording) {
      if (recording.kind === "transcription") {
        elements.voiceStatus.textContent = "Transcribing with Google's online speech-recognition service…";
      }
    } else if (status.interaction_state === "speaking") {
      elements.voiceStatus.textContent = "ARIA is speaking through the local Windows speech service.";
    } else if (status.interaction_state === "error" && status.interaction_error) {
      elements.voiceStatus.textContent = status.interaction_error;
      if (!/no speech|no clear speech/i.test(status.interaction_error)) {
        elements.continuousListening.checked = false;
      }
    } else if (status.interaction_state === "thinking") {
      elements.voiceStatus.textContent = "ARIA is processing your request.";
    } else if (status.transcription_available) {
      elements.voiceStatus.textContent = status.speech_output_ready
        ? "Voice is ready. Start a recording whenever you like."
        : status.speech_error || "Starting local speech output…";
    } else {
      elements.voiceStatus.textContent = "Voice recognition is unavailable. Text chat still works.";
    }

    const selectedVoice = status.selected_voice_id || "";
    const selectedVoiceData = (status.voices || []).find((voice) => voice.id === selectedVoice);
    if (selectedVoiceData?.gender) elements.voiceGender.value = selectedVoiceData.gender;
    const genderFilter = elements.voiceGender.value;
    const filteredVoices = genderFilter
      ? (status.voices || []).filter((voice) => voice.gender === genderFilter)
      : (status.voices || []);
    const optionsKey = JSON.stringify([
      status.voices,
      selectedVoice,
      genderFilter,
      status.speech_output_ready,
    ]);
    if (optionsKey !== voiceOptionsKey) {
      voiceOptionsKey = optionsKey;
      elements.voiceSelect.replaceChildren();
      const defaultOption = document.createElement("option");
      defaultOption.value = "";
      defaultOption.textContent = "System default";
      elements.voiceSelect.append(defaultOption);
      for (const voice of filteredVoices) {
        const option = document.createElement("option");
        option.value = voice.id;
        option.textContent = voice.name;
        elements.voiceSelect.append(option);
      }
      elements.voiceSelect.disabled = !status.speech_output_ready || !filteredVoices.length;
      elements.voiceSelect.value = [...elements.voiceSelect.options].some((option) => option.value === selectedVoice)
        ? selectedVoice
        : "";
      elements.voiceGender.disabled = !status.speech_output_ready || !status.voices?.length;
    }
    elements.stopSpeech.disabled = !["starting", "speaking"].includes(status.speech_state);
    if (status.speech_error) {
      if (!recording) elements.voiceStatus.textContent = status.speech_error;
      if (speechStarted || speechPending) {
        showError(status.speech_error);
        speechStarted = false;
        speechPending = false;
        setState("error");
      }
    }
    const speechEventChanged = status.speech_event_id > lastSpeechEventId;
    if (speechEventChanged) {
      lastSpeechEventId = status.speech_event_id;
      if (stateIsCurrent && status.interaction_state === "speaking") {
        speechStarted = true;
        pulseSpeechActivity();
      }
    }
    if (status.speech_state === "speaking") {
      lastObservedSpeechState = "speaking";
    } else if (
      status.speech_state === "idle"
      && ["starting", "speaking"].includes(lastObservedSpeechState)
    ) {
      if (!status.speech_error) console.info("[ARIA TTS] Speech completed");
      lastObservedSpeechState = "idle";
    } else {
      lastObservedSpeechState = status.speech_state;
    }
    if (stateIsCurrent && status.interaction_state === "speaking") {
      speechStarted = true;
      speechPending = false;
    } else if (
      stateIsCurrent
      && status.interaction_state !== "thinking"
      && (speechStarted || speechPending)
    ) {
      speechStarted = false;
      speechPending = false;
    }
    scheduleContinuousListening();
  } catch (error) {
    transcriptionAvailable = false;
    updateControls();
    elements.voiceStatus.textContent = error.message || "Voice status is unavailable. Text chat still works.";
    if (error.message?.includes("local server is out of date")) showError(error.message);
  } finally {
    voiceStatusRequestInFlight = false;
  }
}

async function speakReply(text, sessionId = interactionId) {
  clearError();
  speechStarted = false;
  const currentInteractionId = sessionId || crypto.randomUUID();
  if (!sessionId) await changeInteractionState("thinking", currentInteractionId);
  speechPending = true;
  try {
    console.info("[ARIA TTS] Starting speech");
    const selectedVoice = elements.voiceSelect.value || null;
    await api("/api/voice/speak", {
      method: "POST",
      body: JSON.stringify({
        text,
        voice_id: selectedVoice,
        interaction_id: currentInteractionId,
      }),
    });
    interactionId = currentInteractionId;
    elements.stopSpeech.disabled = false;
    startInteractionPolling();
    await updateVoiceStatus();
    return true;
  } catch (error) {
    console.error("[ARIA ERROR] TTS request failed", error);
    speechPending = false;
    showError(error.message);
    try {
      await changeInteractionState("error", currentInteractionId, error.message);
    } catch (stateError) {
      console.error("[ARIA ERROR] TTS state recovery failed", stateError);
      setState("error");
    }
    return false;
  }
}

function pulseSpeechActivity() {
  elements.stage.classList.remove("speech-pulse");
  void elements.stage.getBoundingClientRect();
  elements.stage.classList.add("speech-pulse");
  window.clearTimeout(speechPulseTimer);
  speechPulseTimer = window.setTimeout(() => elements.stage.classList.remove("speech-pulse"), 320);
}

function resetMicrophoneVisuals() {
  elements.stage.style.removeProperty("--mic-level");
  elements.nucleusAura.setAttribute("r", "71");
  elements.nucleusAura.style.removeProperty("opacity");
  elements.nucleus.style.removeProperty("filter");
}

function resample(input, inputRate, outputRate) {
  if (inputRate === outputRate) return input;
  const ratio = inputRate / outputRate;
  const output = new Float32Array(Math.floor(input.length / ratio));
  for (let index = 0; index < output.length; index += 1) {
    const start = Math.floor(index * ratio);
    const end = Math.min(Math.floor((index + 1) * ratio), input.length);
    let total = 0;
    for (let sample = start; sample < end; sample += 1) total += input[sample];
    output[index] = total / Math.max(1, end - start);
  }
  return output;
}

function makeWav(samples, sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeString = (offset, value) => {
    for (let index = 0; index < value.length; index += 1) view.setUint8(offset + index, value.charCodeAt(index));
  };
  writeString(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(36, "data");
  view.setUint32(40, samples.length * 2, true);
  for (let index = 0; index < samples.length; index += 1) {
    const value = Math.max(-1, Math.min(1, samples[index]));
    view.setInt16(44 + index * 2, value < 0 ? value * 0x8000 : value * 0x7fff, true);
  }
  return new Blob([buffer], { type: "audio/wav" });
}

async function beginRecording() {
  if (
    !connected
    || recording
    || ["listening", "thinking", "speaking"].includes(elements.stage.dataset.state)
  ) return;
  if (!navigator.mediaDevices?.getUserMedia || !window.AudioContext) {
    showError("This browser cannot capture microphone audio. You can still type your message.");
    return;
  }
  clearError();
  const session = { id: crypto.randomUUID(), kind: "permission", cancelled: false };
  recording = session;
  elements.send.disabled = true;
  elements.mic.disabled = true;
  elements.recordingActions.hidden = false;
  elements.finishRecording.disabled = true;
  elements.cancelRecording.textContent = "Cancel request";
  elements.voiceStatus.textContent = "Waiting for microphone permission. No audio is captured yet.";
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
    if (session.cancelled || recording !== session) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    session.stream = stream;
    const context = new AudioContext();
    session.context = context;
    const source = context.createMediaStreamSource(stream);
    const processor = context.createScriptProcessor(4096, 1, 1);
    const analyser = context.createAnalyser();
    analyser.fftSize = 1024;
    const levels = new Float32Array(analyser.fftSize);
    const mute = context.createGain();
    mute.gain.value = 0;
    const chunks = [];
    source.connect(analyser);
    session.kind = "capture";
    session.source = source;
    session.processor = processor;
    session.analyser = analyser;
    session.levels = levels;
    session.chunks = chunks;
    session.sampleCount = 0;
    session.startedAt = performance.now();
    session.speechStartedAt = null;
    session.silenceStartedAt = null;
    processor.onaudioprocess = (event) => {
      if (recording !== session) return;
      const chunk = new Float32Array(event.inputBuffer.getChannelData(0));
      chunks.push(chunk);
      session.sampleCount += chunk.length;
      if (session.sampleCount >= context.sampleRate * 60) {
        void endRecording({ submit: true, reason: "Recording reached its 60-second limit." });
      }
    };
    source.connect(processor);
    processor.connect(mute);
    mute.connect(context.destination);
    elements.finishRecording.disabled = false;
    elements.cancelRecording.textContent = "Cancel recording";
    elements.voiceStatus.textContent = "Microphone is active. Audio stays in this tab until you stop and transcribe.";
    await changeInteractionState("listening", session.id);
    console.info("[ARIA VOICE] Speech recognition started.");
    monitorMicrophone(session);
  } catch (error) {
    console.error("[ARIA ERROR] Microphone capture failed", error);
    elements.continuousListening.checked = false;
    if (recording === session) recording = null;
    session.stream?.getTracks().forEach((track) => track.stop());
    if (session.context && session.context.state !== "closed") {
      try {
        await session.context.close();
      } catch (closeError) {
        console.error("[ARIA ERROR] Failed to close microphone audio context", closeError);
        showError("The browser could not release its microphone audio context cleanly.");
      }
    }
    elements.recordingActions.hidden = true;
    updateControls();
    if (session.cancelled) {
      elements.voiceStatus.textContent = "Microphone request cancelled. No audio was captured.";
      updateControls();
      return;
    }
    if (error?.name === "NotAllowedError" || error?.name === "PermissionDeniedError" || error?.name === "SecurityError") {
      elements.voiceStatus.textContent = "Microphone permission was denied. Allow access in your browser settings or use text chat.";
    } else if (error?.name === "NotFoundError" || error?.name === "DevicesNotFoundError") {
      elements.voiceStatus.textContent = "No microphone was found. Connect a microphone or use text chat.";
    } else if (error?.name === "NotReadableError" || error?.name === "TrackStartError") {
      elements.voiceStatus.textContent = "The microphone is busy or unavailable. Check your device and try again.";
    } else {
      elements.voiceStatus.textContent = "The microphone could not be started. Check browser and Windows microphone permissions.";
    }
    showError(elements.voiceStatus.textContent);
    try {
      await changeInteractionState("error", session.id, elements.voiceStatus.textContent);
    } catch (stateError) {
      console.error("[ARIA ERROR] Failed to recover microphone interaction state", stateError);
      setState("error");
    }
  }
}

function monitorMicrophone(session) {
  if (recording !== session || session.kind !== "capture") return;
  const now = performance.now();
  session.analyser.getFloatTimeDomainData(session.levels);
  let squareSum = 0;
  for (const sample of session.levels) squareSum += sample * sample;
  const level = Math.min(1, Math.sqrt(squareSum / session.levels.length));
  elements.stage.style.setProperty("--mic-level", level.toFixed(3));
  elements.nucleusAura.setAttribute("r", String(71 + level * 24));
  elements.nucleusAura.style.opacity = String(.42 + level * .52);
  elements.nucleus.style.filter = `drop-shadow(0 0 ${10 + level * 26}px rgba(0, 229, 255, .78))`;

  if (level >= 0.018) {
    if (session.speechStartedAt === null) {
      elements.voiceStatus.textContent = "Speech detected. Release or stop speaking to send for transcription.";
    }
    session.speechStartedAt ??= now;
    session.silenceStartedAt = null;
  } else if (session.speechStartedAt !== null) {
    session.silenceStartedAt ??= now;
  }

  if (now - session.startedAt >= 60_000) {
    void endRecording({ submit: true, reason: "Recording reached its 60-second limit." });
    return;
  }
  if (session.speechStartedAt === null && now - session.startedAt >= 8_000) {
    void endRecording({ submit: false, reason: "No speech was detected. Try again or type your message." });
    return;
  }
  if (session.silenceStartedAt !== null && now - session.silenceStartedAt >= 1_200) {
    void endRecording({ submit: true, reason: "Speech detected and transcribed." });
    return;
  }
  session.frameId = requestAnimationFrame(() => monitorMicrophone(session));
}

async function endRecording({ submit, reason }) {
  if (!recording) return;
  const current = recording;
  if (current.kind === "permission") {
    current.cancelled = true;
    recording = null;
    elements.recordingActions.hidden = true;
    updateControls();
    elements.voiceStatus.textContent = "Microphone request cancelled. No audio was captured.";
    return;
  }
  if (current.kind === "transcription") {
    current.controller.abort();
    return;
  }
  recording = null;
  if (current.frameId) cancelAnimationFrame(current.frameId);
  current.processor.onaudioprocess = null;
  current.source.disconnect();
  current.processor.disconnect();
  current.stream.getTracks().forEach((track) => track.stop());
  const sampleRate = current.context.sampleRate;
  try {
    await current.context.close();
  } catch (closeError) {
    console.error("[ARIA ERROR] Failed to close microphone audio context", closeError);
    showError("The browser could not release its microphone audio context cleanly.");
  }
  resetMicrophoneVisuals();
  elements.recordingActions.hidden = true;
  if (!submit) {
    if (reason?.startsWith("No speech")) {
      await changeInteractionState("error", current.id, reason);
    } else {
      await changeInteractionState("idle", current.id);
    }
    elements.voiceStatus.textContent = reason || "Recording cancelled. No audio was sent.";
    updateControls();
    return;
  }

  const count = current.chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  if (!count) {
    elements.continuousListening.checked = false;
    try {
      await changeInteractionState("error", current.id, "No microphone audio was captured.");
    } catch (error) {
      showError(error.message);
      setState("error");
    }
    elements.voiceStatus.textContent = "No microphone audio was captured. Try again or type a message.";
    updateControls();
    return;
  }
  const combined = new Float32Array(count);
  let offset = 0;
  for (const chunk of current.chunks) {
    combined.set(chunk, offset);
    offset += chunk.length;
  }
  const resampled = resample(combined, sampleRate, 16000);
  const samples = resampled.subarray(0, 16000 * 60);
  const audio = makeWav(samples, 16000);
  elements.voiceStatus.textContent = "Sending this recording to Google for transcription. Raw audio is not saved by ARIA.";
  const controller = new AbortController();
  recording = { kind: "transcription", controller, id: current.id };
  try {
    await changeInteractionState("thinking", current.id);
    const response = await fetch("/api/voice/transcribe", {
      method: "POST",
      headers: {
        "Content-Type": "audio/wav",
        "X-ARIA-Interaction-ID": current.id,
      },
      body: audio,
      signal: controller.signal,
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `Transcription failed (${response.status}).`);
    const transcript = typeof payload.text === "string" ? payload.text.trim() : "";
    if (!transcript) {
      elements.voiceStatus.textContent = "No clear speech was recognized. Try again or type a message.";
      await changeInteractionState("error", current.id, "No clear speech was recognized.");
    } else {
      recording = null;
      elements.voiceStatus.textContent = "Recognized speech. Sending your request to ARIA…";
      console.info("[ARIA INPUT] Speech recognized", { characters: transcript.length });
      const result = await processUserInput(transcript, "voice", {
        voiceInteractionId: current.id,
      });
      if (result.completed) {
        elements.voiceStatus.textContent = result.speechAccepted
          ? "ARIA responded. Local speech is starting; your recording was processed by Google."
          : "ARIA's text response is ready. Local speech could not start.";
      } else {
        elements.continuousListening.checked = false;
      }
    }
  } catch (error) {
    console.error("[ARIA ERROR] Voice transcription or response pipeline failed", error);
    elements.continuousListening.checked = false;
    if (error.name === "AbortError") {
      elements.voiceStatus.textContent = "The browser request was cancelled. Google may already have received the recording.";
      try {
        await changeInteractionState("idle", current.id);
      } catch (stateError) {
        console.error("[ARIA ERROR] Failed to reset cancelled interaction", stateError);
        await updateVoiceStatus();
      }
    } else {
      showError(error.message);
      elements.voiceStatus.textContent = "Transcription unavailable. Text chat is still ready.";
      try {
        await changeInteractionState("error", current.id, error.message);
      } catch (stateError) {
        console.error("[ARIA ERROR] Failed to recover transcription interaction state", stateError);
        setState("error");
      }
    }
  } finally {
    recording = null;
    elements.finishRecording.disabled = true;
    elements.recordingActions.hidden = true;
    updateControls();
    scheduleContinuousListening();
  }
}

function cancelRecording() {
  if (!recording) return;
  if (recording.kind === "permission") {
    void endRecording({ submit: false });
    return;
  }
  if (recording.kind === "transcription") {
    void endRecording({ submit: false });
    return;
  }
  void endRecording({ submit: false, reason: "Recording cancelled. No audio was sent." });
}

async function beginFromMicrophoneButton() {
  if (elements.stage.dataset.state === "speaking") {
    try {
      await api("/api/voice/stop", { method: "POST" });
      await updateVoiceStatus();
    } catch (error) {
      showError(error.message);
      return;
    }
  }
  await beginRecording();
}

async function updateVisionStatus() {
  if (!visionActive) return;
  try {
    const scene = await api("/api/vision/analyze");
    if (scene.status !== "analyzed") {
      elements.visionStatus.textContent = "Camera is active, but no frame is currently available.";
      return;
    }
    elements.visionStatus.textContent = `Camera active · ${scene.face_count} face(s) detected locally. Identity and emotion are not recognized.`;
  } catch (error) {
    elements.visionStatus.textContent = error.message;
    showError(error.message);
    stopVisionPolling();
  }
}

function stopVisionPolling() {
  if (visionPoll) {
    window.clearInterval(visionPoll);
    visionPoll = null;
  }
}

async function toggleVision() {
  elements.visionButton.disabled = true;
  try {
    if (visionActive) {
      await api("/api/vision/stop", { method: "POST" });
      visionActive = false;
      stopVisionPolling();
      elements.visionButton.textContent = "Enable camera";
      elements.visionButton.setAttribute("aria-pressed", "false");
      elements.visionStatus.textContent = "Camera off. Identity and emotion recognition are disabled.";
    } else {
      elements.visionStatus.textContent = "Requesting local camera access…";
      await api("/api/vision/start", {
        method: "POST",
        body: JSON.stringify({ consent: true }),
      });
      visionActive = true;
      elements.visionButton.textContent = "Disable camera";
      elements.visionButton.setAttribute("aria-pressed", "true");
      elements.visionStatus.textContent = "Camera active. Frames are analyzed locally and not retained.";
      await updateVisionStatus();
      if (visionActive && !visionPoll) visionPoll = window.setInterval(updateVisionStatus, 5000);
    }
  } catch (error) {
    elements.visionStatus.textContent = error.message;
    showError(error.message);
  } finally {
    elements.visionButton.disabled = false;
  }
}

async function loadPermissionModes() {
  try {
    const vision = await api("/api/vision/status");
    visionActive = vision.active === true;
    elements.visionButton.textContent = visionActive ? "Disable camera" : "Enable camera";
    elements.visionButton.setAttribute("aria-pressed", String(visionActive));
    if (visionActive) {
      elements.visionStatus.textContent = "Camera active. Frames are analyzed locally and not retained.";
      await updateVisionStatus();
      if (visionActive) visionPoll = window.setInterval(updateVisionStatus, 5000);
    } else if (!vision.available) {
      elements.visionStatus.textContent = "Camera analysis requires the optional OpenCV package.";
      elements.visionButton.disabled = true;
    }
  } catch (error) {
    elements.visionStatus.textContent = error.message;
  }
  try {
    const ambient = await api("/api/ambient/status");
    ambientEnabled = ambient.enabled === true;
    elements.ambientMode.checked = ambientEnabled;
    if (ambientEnabled) startAmbientPolling();
  } catch (error) {
    showError(error.message);
  }
}

function startAmbientPolling() {
  if (ambientPoll) window.clearInterval(ambientPoll);
  ambientPoll = window.setInterval(async () => {
    if (
      !ambientEnabled
      || document.hidden
      || sending
      || elements.input.value.trim()
    ) return;
    try {
      const decision = await api("/api/ambient/evaluate", { method: "POST" });
      if (
        decision.action === "proactive_response"
        && typeof decision.message === "string"
        && elements.stage.dataset.state === "idle"
      ) {
        appendMessage("assistant", decision.message, { speak: false });
      }
    } catch (error) {
      elements.ambientMode.checked = false;
      ambientEnabled = false;
      window.clearInterval(ambientPoll);
      ambientPoll = null;
      showError(error.message);
    }
  }, 60_000);
}

async function setAmbient(enabled) {
  try {
    const result = await api("/api/ambient", {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    });
    ambientEnabled = result.enabled === true;
    elements.ambientMode.checked = ambientEnabled;
    if (ambientPoll) window.clearInterval(ambientPoll);
    ambientPoll = null;
    if (ambientEnabled) startAmbientPolling();
  } catch (error) {
    elements.ambientMode.checked = ambientEnabled;
    showError(error.message);
  }
}

function resizeInput() {
  elements.input.style.height = "auto";
  elements.input.style.height = `${Math.min(elements.input.scrollHeight, 150)}px`;
  updateControls();
}

elements.form.addEventListener("submit", (event) => {
  event.preventDefault();
  void processUserInput(elements.input.value, "text");
});
elements.input.addEventListener("input", resizeInput);
elements.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    void processUserInput(elements.input.value, "text");
  }
});
elements.mic.addEventListener("click", () => void beginFromMicrophoneButton());
elements.continuousListening.addEventListener("change", () => {
  if (!elements.continuousListening.checked) {
    window.clearTimeout(continuousStartTimer);
    if (recording) cancelRecording();
  } else {
    scheduleContinuousListening();
  }
});
elements.voicePersona.addEventListener("change", async () => {
  try {
    await api("/api/voice/persona", {
      method: "PUT",
      body: JSON.stringify({ persona: elements.voicePersona.value }),
    });
    await updateVoiceStatus();
  } catch (error) {
    showError(error.message);
    await updateVoiceStatus();
  }
});
elements.visionButton.addEventListener("click", () => void toggleVision());
elements.ambientMode.addEventListener("change", () => {
  void setAmbient(elements.ambientMode.checked);
});
elements.finishRecording.addEventListener("click", () => void endRecording({
  submit: true,
  reason: "Recording stopped by you.",
}));
elements.cancelRecording.addEventListener("click", cancelRecording);
elements.stopSpeech.addEventListener("click", async () => {
  try {
    await api("/api/voice/stop", { method: "POST" });
    await updateVoiceStatus();
  } catch (error) {
    showError(error.message);
  }
});
elements.voiceSelect.addEventListener("change", async () => {
  try {
    const response = await api("/api/voice/voice", {
      method: "PUT",
      body: JSON.stringify({ voice_id: elements.voiceSelect.value || null }),
    });
    const selectedVoice = elements.voiceSelect.value;
    if (selectedVoice) {
      const voice = [...elements.voiceSelect.options].find((option) => option.value === selectedVoice);
      elements.voiceGender.value = voice?.value ? elements.voiceGender.value : "";
    }
    voiceOptionsKey = "";
    await updateVoiceStatus();
  } catch (error) {
    showError(error.message);
    voiceOptionsKey = "";
    await updateVoiceStatus();
  }
});
elements.voiceGender.addEventListener("change", async () => {
  try {
    if (elements.voiceGender.value) {
      await api("/api/voice/voice", {
        method: "PUT",
        body: JSON.stringify({ gender: elements.voiceGender.value }),
      });
    } else {
      await api("/api/voice/voice", {
        method: "PUT",
        body: JSON.stringify({ voice_id: null }),
      });
    }
    voiceOptionsKey = "";
    await updateVoiceStatus();
  } catch (error) {
    showError(error.message);
    voiceOptionsKey = "";
    await updateVoiceStatus();
  }
});
document.querySelectorAll(".suggestion").forEach((button) => {
  button.addEventListener("click", () =>   void processUserInput(button.textContent, "text"));
});

setState("idle");
void checkHealth();
void loadHistory();
void updateVoiceStatus();
void loadPermissionModes();
statusTimer = window.setInterval(() => {
  void checkHealth();
  void updateVoiceStatus();
}, 4000);
window.addEventListener("beforeunload", () => {
  if (recording) cancelRecording();
  if (visionActive) {
    fetch("/api/vision/stop", { method: "POST", keepalive: true });
  }
  if (ambientEnabled) {
    fetch("/api/ambient", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: false }),
      keepalive: true,
    });
  }
  window.clearInterval(statusTimer);
  if (speechPoll) window.clearInterval(speechPoll);
  if (ambientPoll) window.clearInterval(ambientPoll);
  if (visionPoll) window.clearInterval(visionPoll);
});
