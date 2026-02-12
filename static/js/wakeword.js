import { WakeWordEngine } from "/static/wakeword/WakeWordEngine.js";
import { sendMessage, addMessage } from "./chat.js";

let engine = null;
let active = false;
let recording = false;
let paused = false;
let mediaRecorder = null;
let audioChunks = [];
let silenceTimer = null;
let loaded = false;
let keyword = "hey_jarvis";

const SILENCE_TIMEOUT_MS = 1500;

async function initWakeWord() {
  const btn = document.getElementById("wakeword-toggle");

  btn.classList.remove("hidden");

  // Check if STT is enabled
  try {
    const res = await fetch("/api/stt/status");
    const data = await res.json();
    if (!data.enabled) {
      btn.classList.add("disabled");
      return;
    }
    if (data.wakeword) keyword = data.wakeword;
  } catch {
    btn.classList.add("disabled");
    return;
  }

  btn.addEventListener("click", toggleWakeWord);
}

async function loadEngine() {
  if (loaded) return;
  const btn = document.getElementById("wakeword-toggle");
  btn.textContent = "...";

  // Configure ONNX Runtime WASM paths to match the CDN script
  if (globalThis.ort) {
    globalThis.ort.env.wasm.wasmPaths =
      "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.21.0/dist/";
  }

  engine = new WakeWordEngine({
    keywords: [keyword],
    baseAssetUrl: "/static/wakeword/models",
    detectionThreshold: 0.5,
    cooldownMs: 3000,
  });

  await engine.load();
  loaded = true;

  engine.on("detect", ({ keyword, score }) => {
    console.log(`Wake word detected: ${keyword} (${score.toFixed(2)})`);
    if (!recording && !paused) {
      const btn = document.getElementById("wakeword-toggle");
      btn.classList.add("detected");
      setTimeout(() => {
        btn.classList.remove("detected");
        startRecording();
      }, 100);
    }
  });

  engine.on("speech-end", () => {
    if (recording) {
      clearTimeout(silenceTimer);
      silenceTimer = setTimeout(stopRecording, 500);
    }
  });

  engine.on("speech-start", () => {
    if (recording && silenceTimer) {
      clearTimeout(silenceTimer);
      silenceTimer = null;
    }
  });

  engine.on("error", (err) => {
    console.error("WakeWordEngine error:", err);
  });

  btn.textContent = "Wake";
}

async function toggleWakeWord() {
  const btn = document.getElementById("wakeword-toggle");
  if (active) {
    await engine.stop();
    active = false;
    paused = false;
    btn.classList.remove("active");
    btn.textContent = "Wake";
    if (recording) stopRecording();
  } else {
    try {
      await loadEngine();
      await engine.start();
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

/** Pause wake word detection (e.g. while AI audio is playing) */
function pauseWakeWord() {
  if (!active) return;
  paused = true;
  const btn = document.getElementById("wakeword-toggle");
  btn.classList.add("paused");
  if (engine) engine.setActiveKeywords([]);
}

/** Resume wake word detection after pause */
function resumeWakeWord() {
  if (!active) return;
  paused = false;
  const btn = document.getElementById("wakeword-toggle");
  btn.classList.remove("paused");
  if (engine) engine.setActiveKeywords([keyword]);
}

function startRecording() {
  if (recording) return;
  recording = true;
  // Suppress wake word detection during recording
  if (engine) engine.setActiveKeywords([]);

  navigator.mediaDevices
    .getUserMedia({ audio: true })
    .then((stream) => {
      audioChunks = [];
      mediaRecorder = new MediaRecorder(stream);
      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunks.push(e.data);
      };
      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        recording = false;

        if (audioChunks.length === 0) {
          reactivate();
          return;
        }

        const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType });

        // Pause during transcription + AI response + TTS playback.
        // The websocket audio handler will call resumeWakeWord() when done.
        pauseWakeWord();

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
            resumeWakeWord();
          }
        } catch {
          addMessage("assistant", "STT request failed.");
          resumeWakeWord();
        }

        // If no TTS audio will play, resume now.
        // If TTS audio plays, websocket.js will call resumeWakeWord() when audio ends.
        // Use a fallback timeout to resume in case no audio comes.
        setTimeout(() => {
          if (paused && active) resumeWakeWord();
        }, 5000);
      };
      mediaRecorder.start();

      // Safety timeout — stop after silence
      silenceTimer = setTimeout(stopRecording, SILENCE_TIMEOUT_MS);
    })
    .catch((err) => {
      console.warn("Recording failed:", err);
      recording = false;
      reactivate();
    });
}

function stopRecording() {
  clearTimeout(silenceTimer);
  silenceTimer = null;
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
  } else {
    recording = false;
    reactivate();
  }
}

/** Re-enable wake word keyword after recording ends */
function reactivate() {
  if (active && engine && !paused) {
    engine.setActiveKeywords([keyword]);
  }
}

export { initWakeWord, pauseWakeWord, resumeWakeWord };
