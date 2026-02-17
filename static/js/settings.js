import {
  setShowToolCalls,
  getShowToolCalls,
  clearMessages,
  loadMessages,
} from "./chat.js";
import { authFetch } from "./auth.js";

const panel = document.getElementById("settings-panel");
const overlay = document.getElementById("settings-overlay");
const openBtn = document.getElementById("settings-btn");
const closeBtn = document.getElementById("settings-close");
const toolcallCheckbox = document.getElementById("setting-toolcalls");
const newChatBtn = document.getElementById("new-chat-btn");
const hideUiBtn = document.getElementById("hide-ui-btn");
const chatList = document.getElementById("chat-list");
const layoutCheckbox = document.getElementById("setting-layout");

let currentSessionId = null;

function openPanel() {
  panel.classList.add("open");
  overlay.classList.remove("hidden");
  loadChatList();
}

function closePanel() {
  panel.classList.remove("open");
  overlay.classList.add("hidden");
}

function formatDate(isoString) {
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return isoString;
  }
}

async function loadChatList() {
  try {
    const res = await authFetch("/api/chats");
    const data = await res.json();
    const sessions = data.sessions || [];
    currentSessionId = data.current || null;

    chatList.innerHTML = "";
    for (const session of sessions) {
      const item = document.createElement("div");
      item.className = "chat-list-item";
      if (session.id === currentSessionId) {
        item.classList.add("active");
      }

      const dateSpan = document.createElement("span");
      dateSpan.className = "chat-date";
      dateSpan.textContent = session.title || formatDate(session.started_at);

      const countSpan = document.createElement("span");
      countSpan.className = "chat-count";
      countSpan.textContent = `${session.message_count} msg`;

      item.appendChild(dateSpan);
      item.appendChild(countSpan);

      item.addEventListener("click", () => loadChat(session.id));
      chatList.appendChild(item);
    }
  } catch (e) {
    console.error("Failed to load chat list:", e);
  }
}

async function loadChat(id) {
  try {
    const res = await authFetch("/api/chats/load", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    const data = await res.json();
    if (data.messages) {
      loadMessages(data.messages);
      currentSessionId = id;
      loadChatList();
    }
  } catch (e) {
    console.error("Failed to load chat:", e);
  }
}

async function newChat() {
  try {
    const res = await authFetch("/api/chats/new", { method: "POST" });
    const data = await res.json();
    if (data.id) {
      clearMessages();
      currentSessionId = data.id;
      loadChatList();
    }
  } catch (e) {
    console.error("Failed to create new chat:", e);
  }
}

function initSettings() {
  // Sync checkbox with current state
  toolcallCheckbox.checked = getShowToolCalls();

  openBtn.addEventListener("click", openPanel);
  closeBtn.addEventListener("click", closePanel);
  overlay.addEventListener("click", closePanel);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && panel.classList.contains("open")) {
      closePanel();
    }
  });

  toolcallCheckbox.addEventListener("change", () => {
    setShowToolCalls(toolcallCheckbox.checked);
  });

  newChatBtn.addEventListener("click", newChat);

  // Layout toggle
  const isSplit = localStorage.getItem("layout") === "split";
  layoutCheckbox.checked = isSplit;
  if (isSplit) {
    document.body.classList.add("layout-split");
    window.dispatchEvent(new Event("resize"));
  }
  layoutCheckbox.addEventListener("change", () => {
    document.body.classList.toggle("layout-split", layoutCheckbox.checked);
    localStorage.setItem(
      "layout",
      layoutCheckbox.checked ? "split" : "default",
    );
    window.dispatchEvent(new Event("resize"));
  });

  hideUiBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    closePanel();
    document.body.classList.add("ui-hidden");
  });

  document.addEventListener("click", (e) => {
    if (!document.body.classList.contains("ui-hidden")) return;
    if (e.target.closest("#heartbeat-indicator, #voice-indicator")) return;
    document.body.classList.remove("ui-hidden");
  });

  // Load initial chat list
  loadChatList();
}

export { initSettings };
