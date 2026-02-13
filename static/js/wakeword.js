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
let modelFile = null;

const SILENCE_TIMEOUT_MS = 10000;

async function initWakeWord() {
  const btn = document.getElementById("wakeword-toggle");

  // Check if STT and wakeword are enabled
  try {
    const res = await fetch("/api/stt/status");
    const data = await res.json();
    if (!data.wakeword_enabled) {
      return;
    }
    if (!data.enabled) {
      console.warn(
        "Wake word is enabled but STT is disabled. Enable STT in config to use wake word.",
      );
      return;
    }
    if (data.wakeword) keyword = data.wakeword;
    if (data.wakeword_model_file) modelFile = data.wakeword_model_file;
  } catch {
    return;
  }

  btn.classList.remove("hidden");

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

  const engineOpts = {
    keywords: [keyword],
    baseAssetUrl: "/static/wakeword/models",
    detectionThreshold: 0.5,
    cooldownMs: 3000,
  };
  if (modelFile) {
    engineOpts.modelFiles = { [keyword]: modelFile };
  }
  engine = new WakeWordEngine(engineOpts);

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
      silenceTimer = setTimeout(stopRecording, 1000);
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

        // Re-enable wake word detection now that send is complete.
        // If TTS audio is playing, the websocket handler will have
        // called pauseWakeWord() and will resumeWakeWord() when done,
        // so reactivate() will be a no-op in that case (paused=true).
        reactivate();
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
