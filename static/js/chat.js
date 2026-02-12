const chatMessages = document.getElementById("chat-messages");

function addMessage(role, text) {
  const el = document.createElement("div");
  el.className = `chat-msg ${role}`;
  el.textContent = text;
  chatMessages.appendChild(el);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function initChat() {
  const chatInput = document.getElementById("chat-input");
  const chatSend = document.getElementById("chat-send");

  let sending = false;
  async function sendMessage() {
    const text = chatInput.value.trim();
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

  chatSend.addEventListener("click", sendMessage);
  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      sendMessage();
    }
  });
}

export { addMessage, initChat };
