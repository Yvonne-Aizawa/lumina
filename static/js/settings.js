import { setShowToolCalls, getShowToolCalls } from "./chat.js";

const panel = document.getElementById("settings-panel");
const overlay = document.getElementById("settings-overlay");
const openBtn = document.getElementById("settings-btn");
const closeBtn = document.getElementById("settings-close");
const toolcallCheckbox = document.getElementById("setting-toolcalls");

function openPanel() {
  panel.classList.add("open");
  overlay.classList.remove("hidden");
}

function closePanel() {
  panel.classList.remove("open");
  overlay.classList.add("hidden");
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
}

export { initSettings };
