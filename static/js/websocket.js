import { playAnimationByName } from "./animations.js";
import { addMessage, addToolCall } from "./chat.js";

const heartbeatIndicator = document.getElementById("heartbeat-indicator");

function connectWebSocket() {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${protocol}//${location.host}/ws`);

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
      } else if (msg.action === "audio" && msg.data) {
        const bytes = Uint8Array.from(atob(msg.data), (c) => c.charCodeAt(0));
        const blob = new Blob([bytes], { type: "audio/wav" });
        const audio = new Audio(URL.createObjectURL(blob));
        audio.play().catch((e) => console.warn("Audio playback failed:", e));
      } else if (msg.action === "heartbeat") {
        heartbeatIndicator.classList.toggle("hidden", msg.status !== "start");
      }
    } catch (e) {
      console.warn("Invalid WebSocket message:", event.data);
    }
  };

  ws.onclose = () => {
    console.log("WebSocket disconnected, reconnecting in 2s...");
    setTimeout(connectWebSocket, 2000);
  };

  ws.onerror = (err) => {
    console.error("WebSocket error:", err);
    ws.close();
  };
}

export { connectWebSocket };
