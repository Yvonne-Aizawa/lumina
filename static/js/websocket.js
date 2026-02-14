import { getToken } from "./auth.js";
import { playAnimationByName } from "./animations.js";
import { addMessage, addToolCall } from "./chat.js";
import {
  pauseWakeWord,
  resumeWakeWord,
  onWakeWordDetected,
  startListenWindow,
  setVoiceIndicator,
} from "./wakeword.js";

const heartbeatIndicator = document.getElementById("heartbeat-indicator");
let currentAudio = null;
let ws = null;

function getWebSocket() {
  return ws;
}

function connectWebSocket() {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const token = getToken();
  const query = token ? `?token=${encodeURIComponent(token)}` : "";
  ws = new WebSocket(`${protocol}//${location.host}/ws${query}`);

  ws.onopen = () => {
    console.log("WebSocket connected");
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.action === "play" && msg.animation) {
        playAnimationByName(msg.animation);
      } else if (msg.action === "chat" && msg.content) {
        addMessage("assistant", msg.content);
      } else if (msg.action === "tool_call" && msg.name) {
        addToolCall(msg.name, msg.arguments);
      } else if (msg.action === "wakeword_detected") {
        onWakeWordDetected(msg.keyword, msg.score);
      } else if (msg.action === "audio" && msg.data) {
        // Stop any currently playing audio to prevent overlapping
        if (currentAudio) {
          currentAudio.onended = null;
          currentAudio.onerror = null;
          currentAudio.pause();
          currentAudio = null;
        }
        if (document.hidden) return;
        pauseWakeWord();
        setVoiceIndicator("playing");
        const bytes = Uint8Array.from(atob(msg.data), (c) => c.charCodeAt(0));
        const blob = new Blob([bytes], { type: "audio/wav" });
        const audio = new Audio(URL.createObjectURL(blob));
        currentAudio = audio;
        audio.onended = () => {
          currentAudio = null;
          resumeWakeWord();
          setVoiceIndicator("listening");
          startListenWindow();
        };
        audio.onerror = () => {
          currentAudio = null;
          resumeWakeWord();
          setVoiceIndicator("listening");
        };
        audio.play().catch((e) => {
          console.warn("Audio playback failed:", e);
          currentAudio = null;
          resumeWakeWord();
          setVoiceIndicator("listening");
        });
      } else if (msg.action === "heartbeat") {
        heartbeatIndicator.classList.toggle("hidden", msg.status !== "start");
      }
    } catch (e) {
      console.warn("Invalid WebSocket message:", event.data);
    }
  };

  ws.onclose = () => {
    console.log("WebSocket disconnected, reconnecting in 2s...");
    ws = null;
    setTimeout(connectWebSocket, 2000);
  };

  ws.onerror = (err) => {
    console.error("WebSocket error:", err);
    ws.close();
  };
}

export { connectWebSocket, getWebSocket };
