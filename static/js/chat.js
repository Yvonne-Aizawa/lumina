const chatMessages = document.getElementById("chat-messages");
const chatInput = document.getElementById("chat-input");
const chatSend = document.getElementById("chat-send");
const chatMic = document.getElementById("chat-mic");

let sending = false;

function addMessage(role, text) {
  const el = document.createElement("div");
  el.className = `chat-msg ${role}`;
  if (role === "assistant" && typeof marked !== "undefined") {
    el.innerHTML = marked.parse(text);
  } else {
    el.textContent = text;
  }
  chatMessages.appendChild(el);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addToolCall(name, args) {
  const el = document.createElement("div");
  el.className = "chat-msg tool-call";
  const argsStr =
    args && Object.keys(args).length
      ? Object.entries(args)
          .map(([k, v]) => `${k}: ${v}`)
          .join(", ")
      : "";
  el.textContent = argsStr ? `${name}(${argsStr})` : `${name}()`;
  chatMessages.appendChild(el);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function sendMessage(text) {
  text = text || chatInput.value.trim();
  if (!text || sending) return;

  sending = true;
  chatInput.value = "";
  chatSend.disabled = true;
  addMessage("user", text);

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    const data = await res.json();
    if (data.response) {
      addMessage("assistant", data.response);
    } else if (data.error) {
      addMessage("assistant", `Error: ${data.error}`);
    }
  } catch (e) {
    addMessage("assistant", "Failed to reach server.");
  }

  sending = false;
  chatSend.disabled = false;
  chatInput.focus();
}

function initChat() {
  chatSend.addEventListener("click", () => sendMessage());
  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      sendMessage();
    }
  });

  // --- STT mic button ---
  fetch("/api/stt/status")
    .then((r) => r.json())
    .then((data) => {
      if (data.enabled) chatMic.classList.remove("hidden");
    })
    .catch(() => {});

  let mediaRecorder = null;
  let audioChunks = [];

  function startRecording() {
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
          if (audioChunks.length === 0) return;

          const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType });
          chatMic.textContent = "...";
          chatMic.disabled = true;

          try {
            const form = new FormData();
            form.append("file", blob, "recording.webm");
            const res = await fetch("/api/transcribe", {
              method: "POST",
              body: form,
            });
            const data = await res.json();
            if (data.text) {
              sendMessage(data.text);
            } else if (data.error) {
              addMessage("assistant", `STT error: ${data.error}`);
            }
          } catch (e) {
            addMessage("assistant", "STT request failed.");
          }

          chatMic.textContent = "Mic";
          chatMic.disabled = false;
          chatMic.classList.remove("recording");
        };
        mediaRecorder.start();
        chatMic.classList.add("recording");
      })
      .catch((err) => {
        console.warn("Mic access denied:", err);
        addMessage("assistant", "Microphone access denied.");
      });
  }

  function stopRecording() {
    if (mediaRecorder && mediaRecorder.state === "recording") {
      mediaRecorder.stop();
    }
  }

  chatMic.addEventListener("mousedown", startRecording);
  chatMic.addEventListener("mouseup", stopRecording);
  chatMic.addEventListener("mouseleave", stopRecording);
  chatMic.addEventListener("touchstart", (e) => {
    e.preventDefault();
    startRecording();
  });
  chatMic.addEventListener("touchend", (e) => {
    e.preventDefault();
    stopRecording();
  });
}

export { addMessage, addToolCall, sendMessage, initChat };
