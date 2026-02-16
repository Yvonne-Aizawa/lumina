import { authFetch, checkAuth, initAuth } from "./auth.js";

const list = document.getElementById("memory-list");
const detail = document.getElementById("memory-detail");
const detailId = document.getElementById("detail-id");
const detailContent = document.getElementById("detail-content");
const detailMeta = document.getElementById("detail-meta");
const detailStatus = document.getElementById("detail-status");
const searchInput = document.getElementById("memory-search");
const countEl = document.getElementById("memory-count");
const saveBtn = document.getElementById("detail-save");
const deleteBtn = document.getElementById("detail-delete");
const closeBtn = document.getElementById("detail-close");

let entries = [];
let selectedId = null;

async function loadEntries() {
  try {
    const res = await authFetch("/api/vector");
    const data = await res.json();
    if (data.error) {
      list.innerHTML = `<div class="memory-empty">${data.error}</div>`;
      countEl.textContent = "";
      return;
    }
    entries = data.entries || [];
    countEl.textContent = `${entries.length} entries`;
    renderList();
  } catch (e) {
    list.innerHTML = `<div class="memory-empty">Failed to load entries.</div>`;
  }
}

function renderList() {
  const query = searchInput.value.toLowerCase().trim();
  const filtered = query
    ? entries.filter(
        (e) =>
          e.id.toLowerCase().includes(query) ||
          e.content.toLowerCase().includes(query),
      )
    : entries;

  list.innerHTML = "";
  if (filtered.length === 0) {
    list.innerHTML = `<div class="memory-empty">${query ? "No matches." : "No entries yet."}</div>`;
    return;
  }

  for (const entry of filtered) {
    const item = document.createElement("div");
    item.className = "memory-item";
    if (entry.id === selectedId) item.classList.add("active");

    const id = document.createElement("div");
    id.className = "memory-item-id";
    id.textContent = entry.id;

    const preview = document.createElement("div");
    preview.className = "memory-item-preview";
    preview.textContent =
      entry.content.length > 120
        ? entry.content.slice(0, 120) + "..."
        : entry.content;

    item.appendChild(id);
    item.appendChild(preview);
    item.addEventListener("click", () => selectEntry(entry.id));
    list.appendChild(item);
  }
}

function selectEntry(id) {
  selectedId = id;
  const entry = entries.find((e) => e.id === id);
  if (!entry) return;

  detailId.textContent = entry.id;
  detailContent.value = entry.content;
  detailStatus.textContent = "";

  const meta = entry.metadata || {};
  const keys = Object.keys(meta);
  if (keys.length > 0) {
    detailMeta.textContent = keys.map((k) => `${k}: ${meta[k]}`).join(", ");
    detailMeta.classList.remove("hidden");
  } else {
    detailMeta.classList.add("hidden");
  }

  detail.classList.remove("hidden");
  renderList();
}

async function saveEntry() {
  if (!selectedId) return;
  detailStatus.textContent = "Saving...";
  detailStatus.className = "";
  try {
    const res = await authFetch(
      `/api/vector/${encodeURIComponent(selectedId)}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: detailContent.value }),
      },
    );
    const data = await res.json();
    if (data.error) {
      detailStatus.textContent = data.error;
      detailStatus.className = "status-error";
      return;
    }
    detailStatus.textContent = "Saved.";
    detailStatus.className = "status-ok";
    const entry = entries.find((e) => e.id === selectedId);
    if (entry) entry.content = detailContent.value;
    renderList();
  } catch (e) {
    detailStatus.textContent = "Save failed.";
    detailStatus.className = "status-error";
  }
}

async function deleteEntry() {
  if (!selectedId) return;
  if (!confirm(`Delete "${selectedId}"?`)) return;
  try {
    const res = await authFetch(
      `/api/vector/${encodeURIComponent(selectedId)}`,
      {
        method: "DELETE",
      },
    );
    const data = await res.json();
    if (data.error) {
      detailStatus.textContent = data.error;
      detailStatus.className = "status-error";
      return;
    }
    entries = entries.filter((e) => e.id !== selectedId);
    selectedId = null;
    detail.classList.add("hidden");
    countEl.textContent = `${entries.length} entries`;
    renderList();
  } catch (e) {
    detailStatus.textContent = "Delete failed.";
    detailStatus.className = "status-error";
  }
}

function closeDetail() {
  selectedId = null;
  detail.classList.add("hidden");
  renderList();
}

async function init() {
  initAuth();
  const ok = await checkAuth();
  if (!ok) return;

  saveBtn.addEventListener("click", saveEntry);
  deleteBtn.addEventListener("click", deleteEntry);
  closeBtn.addEventListener("click", closeDetail);
  searchInput.addEventListener("input", renderList);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !detail.classList.contains("hidden")) {
      closeDetail();
    }
    if (e.ctrlKey && e.key === "s" && !detail.classList.contains("hidden")) {
      e.preventDefault();
      saveEntry();
    }
  });

  await loadEntries();
}

init();
