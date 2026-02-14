import { sendMessage, addMessage } from "./chat.js";
import { getWebSocket } from "./websocket.js";

let active = false;
let recording = false;
let paused = false;
let mediaRecorder = null;
let audioChunks = [];
let silenceTimer = null;
let keyword = "hey_jarvis";

let audioContext = null;
let workletNode = null;
let mediaStream = null;

const SILENCE_TIMEOUT_MS = 10000;
const SPEECH_END_DELAY_MS = 1000;
const TARGET_SAMPLE_RATE = 16000;
const FRAME_SIZE = 1280;

// AudioWorklet processor code: resamples to 16kHz and outputs Int16 PCM chunks
const AUDIO_PROCESSOR = `
class AudioProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const targetRate = (options.processorOptions && options.processorOptions.targetSampleRate) || 16000;
    this._resampleRatio = sampleRate / targetRate;
    this._frameSize = (options.processorOptions && options.processorOptions.frameSize) || 1280;
    this._buffer = new Float32Array(this._frameSize);
    this._pos = 0;
    this._resamplePos = 0;
    this._inputBuf = [];
  }

  process(inputs) {
    const input = inputs[0][0];
    if (!input) return true;

    for (let i = 0; i < input.length; i++) {
      this._inputBuf.push(input[i]);
    }

    while (this._resamplePos < this._inputBuf.length - 1) {
      const idx = Math.floor(this._resamplePos);
      const frac = this._resamplePos - idx;
      const sample = this._inputBuf[idx] * (1 - frac) + this._inputBuf[idx + 1] * frac;
      this._buffer[this._pos++] = sample;
      this._resamplePos += this._resampleRatio;

      if (this._pos === this._frameSize) {
        // Convert float32 to int16
        const int16 = new Int16Array(this._frameSize);
        for (let j = 0; j < this._frameSize; j++) {
          const s = Math.max(-1, Math.min(1, this._buffer[j]));
          int16[j] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }
        this.port.postMessage(int16.buffer, [int16.buffer]);
        this._buffer = new Float32Array(this._frameSize);
        this._pos = 0;
      }
    }

    const consumed = Math.floor(this._resamplePos);
    if (consumed > 0) {
      this._inputBuf = this._inputBuf.slice(consumed);
      this._resamplePos -= consumed;
    }

    return true;
  }
}
registerProcessor('audio-processor', AudioProcessor);
`;

async function initWakeWord() {
  const btn = document.getElementById("wakeword-toggle");

  try {
    const res = await fetch("/api/stt/status");
    const data = await res.json();
    if (!data.wakeword_enabled) return;
    if (data.wakeword) keyword = data.wakeword;
  } catch {
    return;
  }

  btn.classList.remove("hidden");
  btn.addEventListener("click", toggleWakeWord);
}

async function toggleWakeWord() {
  const btn = document.getElementById("wakeword-toggle");
  if (active) {
    stopStreaming();
    active = false;
    paused = false;
    btn.classList.remove("active");
    btn.textContent = "Wake";
    if (recording) stopRecording();
  } else {
    try {
      btn.textContent = "...";
      await startStreaming();
      active = true;
      paused = false;
      btn.classList.add("active");
      btn.textContent = "Wake";
    } catch (err) {
      console.error("Wake word start failed:", err);
      addMessage("assistant", `Wake word failed: ${err.message}`);
      btn.textContent = "Wake";
    }
  }
}

async function startStreaming() {
  mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });

  audioContext = new AudioContext();
  const source = audioContext.createMediaStreamSource(mediaStream);

  const blob = new Blob([AUDIO_PROCESSOR], { type: "application/javascript" });
  const workletURL = URL.createObjectURL(blob);
  await audioContext.audioWorklet.addModule(workletURL);
  URL.revokeObjectURL(workletURL);

  workletNode = new AudioWorkletNode(audioContext, "audio-processor", {
    processorOptions: {
      targetSampleRate: TARGET_SAMPLE_RATE,
      frameSize: FRAME_SIZE,
    },
  });

  workletNode.port.onmessage = (event) => {
    const ws = getWebSocket();
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (paused || recording) return;
    ws.send(event.data);
  };

  source.connect(workletNode);
  workletNode.connect(audioContext.destination);
  console.log("[wakeword] Streaming started", {
    sampleRate: audioContext.sampleRate,
    targetRate: TARGET_SAMPLE_RATE,
  });
}

function stopStreaming() {
  if (workletNode) {
    workletNode.port.onmessage = null;
    workletNode.disconnect();
    workletNode = null;
  }
  if (audioContext && audioContext.state !== "closed") {
    audioContext.close();
  }
  audioContext = null;
  if (mediaStream) {
    mediaStream.getTracks().forEach((t) => t.stop());
    mediaStream = null;
  }
  console.log("[wakeword] Streaming stopped");
}

/** Called by websocket.js when server sends a detection event */
function onWakeWordDetected(kw, score) {
  console.log(`[wakeword] Detected: ${kw} (${score.toFixed(2)})`);
  if (recording || paused || !active) return;
  const btn = document.getElementById("wakeword-toggle");
  btn.classList.add("detected");
  setTimeout(() => {
    btn.classList.remove("detected");
    startRecording();
  }, 100);
}

/** Pause wake word detection (e.g. while AI audio is playing) */
function pauseWakeWord() {
  if (!active) return;
  paused = true;
  const ws = getWebSocket();
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ action: "wakeword_pause" }));
  }
  const btn = document.getElementById("wakeword-toggle");
  btn.classList.add("paused");
}

/** Resume wake word detection after pause */
function resumeWakeWord() {
  if (!active) return;
  paused = false;
  const ws = getWebSocket();
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ action: "wakeword_resume" }));
  }
  const btn = document.getElementById("wakeword-toggle");
  btn.classList.remove("paused");
}

function startRecording() {
  if (recording) return;

  // Reuse the existing mic stream
  if (!mediaStream || !mediaStream.active) {
    console.error("[wakeword] No active mic stream for recording");
    return;
  }

  recording = true;
  audioChunks = [];
  mediaRecorder = new MediaRecorder(mediaStream);
  mediaRecorder.ondataavailable = (e) => {
    if (e.data.size > 0) audioChunks.push(e.data);
  };
  mediaRecorder.onstop = async () => {
    recording = false;

    if (audioChunks.length === 0) return;

    const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType });

    try {
      const form = new FormData();
      form.append("file", blob, "recording.webm");
      const res = await fetch("/api/transcribe", {
        method: "POST",
        body: form,
      });
      const data = await res.json();
      if (data.text) {
        await sendMessage(data.text);
      } else if (data.error) {
        addMessage("assistant", `STT error: ${data.error}`);
      }
    } catch {
      addMessage("assistant", "STT request failed.");
    }
  };
  mediaRecorder.start();
  silenceTimer = setTimeout(stopRecording, SILENCE_TIMEOUT_MS);
}

function stopRecording() {
  clearTimeout(silenceTimer);
  silenceTimer = null;
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
  } else {
    recording = false;
  }
}

export { initWakeWord, pauseWakeWord, resumeWakeWord, onWakeWordDetected };
