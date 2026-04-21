const STORAGE_KEY = "lumakit-chats-v1";
const ACTIVE_KEY = "lumakit-active-chat";

const state = {
  chats: [],
  activeId: null,
  settings: null,
  sending: false,
  sceneContext: null,
};

const el = {
  chatList: document.getElementById("chat-list"),
  newChat: document.getElementById("new-chat"),
  chatTitle: document.getElementById("chat-title"),
  messages: document.getElementById("message-list"),
  input: document.getElementById("composer-input"),
  sendBtn: document.getElementById("send-button"),
  modelPillText: document.getElementById("model-pill-text"),
  settingsModal: document.getElementById("settings-modal"),
  settingsError: document.getElementById("settings-error"),
  openSettings: document.getElementById("open-settings"),
  saveSettings: document.getElementById("save-settings"),
  providerSwitch: document.getElementById("provider-switch"),
  openaiModel: document.getElementById("openai-model"),
  anthropicModel: document.getElementById("anthropic-model"),
  ollamaModel: document.getElementById("ollama-model"),
  openaiKey: document.getElementById("openai-api-key"),
  anthropicKey: document.getElementById("anthropic-api-key"),
};

function uid() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

function loadChats() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) state.chats = JSON.parse(raw);
  } catch {}
  state.activeId = localStorage.getItem(ACTIVE_KEY);
  if (!state.chats.length) {
    createChat();
  } else if (!state.chats.find((c) => c.id === state.activeId)) {
    state.activeId = state.chats[0].id;
  }
}

function persist() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state.chats));
  if (state.activeId) localStorage.setItem(ACTIVE_KEY, state.activeId);
}

function activeChat() {
  return state.chats.find((c) => c.id === state.activeId);
}

function createChat() {
  const chat = { id: uid(), title: "New Chat", messages: [], createdAt: Date.now() };
  state.chats.unshift(chat);
  state.activeId = chat.id;
  persist();
  renderChatList();
  renderMessages();
  renderTitle();
  el.input.focus();
}

function deleteChat(id) {
  state.chats = state.chats.filter((c) => c.id !== id);
  if (state.activeId === id) {
    state.activeId = state.chats[0]?.id || null;
  }
  if (!state.chats.length) createChat();
  persist();
  renderChatList();
  renderMessages();
  renderTitle();
}

function selectChat(id) {
  state.activeId = id;
  persist();
  renderChatList();
  renderMessages();
  renderTitle();
}

function renderChatList() {
  el.chatList.innerHTML = "";
  for (const chat of state.chats) {
    const item = document.createElement("button");
    item.className = "chat-item" + (chat.id === state.activeId ? " active" : "");
    item.innerHTML = `<span class="chat-item-title"></span><span class="chat-item-close" aria-label="Delete">×</span>`;
    item.querySelector(".chat-item-title").textContent = chat.title || "New Chat";
    item.addEventListener("click", (e) => {
      if (e.target.classList.contains("chat-item-close")) {
        e.stopPropagation();
        deleteChat(chat.id);
        return;
      }
      selectChat(chat.id);
    });
    el.chatList.appendChild(item);
  }
}

function renderTitle() {
  const chat = activeChat();
  el.chatTitle.textContent = chat?.title || "New Chat";
}

function renderMessages() {
  el.messages.innerHTML = "";
  const chat = activeChat();
  if (!chat || !chat.messages.length) {
    const empty = document.createElement("div");
    empty.className = "empty-hint";
    empty.innerHTML = `<h3>How can I help with Blender?</h3><p>Ask about modeling, modifiers, materials, animation, scripting, or your current scene.</p>`;
    el.messages.appendChild(empty);
    return;
  }

  for (const m of chat.messages) {
    const wrap = document.createElement("div");
    wrap.className = "msg " + m.role + (m.state ? " " + m.state : "");
    const bubble = document.createElement("div");
    bubble.className = "msg-bubble";
    bubble.innerHTML = renderContent(m.content);
    wrap.appendChild(bubble);
    el.messages.appendChild(wrap);
  }
  el.messages.scrollTop = el.messages.scrollHeight;
}

function renderContent(text) {
  const escape = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let out = "";
  const parts = text.split(/(```[\s\S]*?```)/g);
  for (const part of parts) {
    if (part.startsWith("```") && part.endsWith("```")) {
      const body = part.slice(3, -3).replace(/^[a-zA-Z0-9_-]*\n/, "");
      out += `<pre><code>${escape(body)}</code></pre>`;
    } else {
      let seg = escape(part);
      seg = seg.replace(/`([^`\n]+)`/g, "<code>$1</code>");
      seg = seg.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
      out += seg;
    }
  }
  return out;
}

async function loadState() {
  try {
    const res = await fetch("/api/state");
    const payload = await res.json();
    state.sceneContext = payload.scene_context;
    state.settings = payload.settings;
    renderSettings();
    renderModelPill();
  } catch {}
}

function renderSettings() {
  const s = state.settings || {};
  state.settings.provider = s.provider || "openai";
  el.openaiModel.value = s.openai_model || "gpt-5";
  el.anthropicModel.value = s.anthropic_model || "claude-sonnet-4-20250514";
  el.ollamaModel.value = s.ollama_model || "ministral-3:14b-cloud";
  el.openaiKey.placeholder = s.openai_api_key_configured ? "API key saved locally" : "Paste an API key to enable OpenAI";
  el.anthropicKey.placeholder = s.anthropic_api_key_configured ? "API key saved locally" : "Paste an API key to enable Anthropic";
  renderProviderPanels();
}

function renderProviderPanels() {
  const p = state.settings?.provider || "openai";
  document.querySelectorAll(".provider-chip").forEach((b) => b.classList.toggle("active", b.dataset.provider === p));
  document.querySelectorAll(".provider-panel").forEach((panel) => panel.classList.toggle("hidden", panel.dataset.panel !== p));
}

function renderModelPill() {
  const s = state.settings || {};
  const p = s.provider || "openai";
  const model = p === "openai" ? s.openai_model : p === "anthropic" ? s.anthropic_model : s.ollama_model;
  el.modelPillText.textContent = model || p;
}

function showSettingsError(msg) {
  el.settingsError.textContent = msg;
  el.settingsError.classList.remove("hidden");
}
function clearSettingsError() {
  el.settingsError.classList.add("hidden");
  el.settingsError.textContent = "";
}

async function saveSettings() {
  clearSettingsError();
  const provider = state.settings.provider;
  const s = state.settings || {};

  if (provider === "openai") {
    const hasKey = el.openaiKey.value.trim() || s.openai_api_key_configured;
    if (!hasKey) {
      showSettingsError("OpenAI requires an API key. Paste one above to continue, or switch to Ollama for a local option.");
      return;
    }
  }
  if (provider === "anthropic") {
    const hasKey = el.anthropicKey.value.trim() || s.anthropic_api_key_configured;
    if (!hasKey) {
      showSettingsError("Anthropic requires an API key. Paste one above to continue, or switch to Ollama for a local option.");
      return;
    }
  }

  const payload = {
    provider,
    openai_model: el.openaiModel.value.trim(),
    anthropic_model: el.anthropicModel.value.trim(),
    ollama_model: el.ollamaModel.value.trim(),
    openai_api_key: el.openaiKey.value.trim(),
    anthropic_api_key: el.anthropicKey.value.trim(),
  };
  const res = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) {
    showSettingsError(data.error || "Could not save settings");
    return;
  }
  state.settings = data.settings;
  el.openaiKey.value = "";
  el.anthropicKey.value = "";
  renderSettings();
  renderModelPill();
  closeSettings();
}

async function sendMessage() {
  if (state.sending) return;
  const content = el.input.value.trim();
  if (!content) return;

  const chat = activeChat();
  if (!chat) return;

  state.sending = true;
  updateSendBtn();

  if (!chat.messages.length) {
    chat.title = content.slice(0, 40) + (content.length > 40 ? "…" : "");
    renderTitle();
    renderChatList();
  }

  const userMsg = { role: "user", content };
  const pending = { role: "assistant", content: "Thinking…", state: "pending" };
  chat.messages.push(userMsg, pending);
  el.input.value = "";
  autosize();
  persist();
  renderMessages();

  const s = state.settings || {};
  const provider = s.provider;
  const model = provider === "openai" ? el.openaiModel.value.trim() : provider === "anthropic" ? el.anthropicModel.value.trim() : el.ollamaModel.value.trim();

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider,
        model,
        messages: chat.messages.filter((m) => m.state !== "pending"),
      }),
    });
    const payload = await res.json();
    if (!res.ok) throw new Error(payload.error || "Request failed");
    pending.content = payload.content;
    pending.state = "done";
  } catch (e) {
    pending.content = `Error: ${e.message}`;
    pending.state = "error";
  } finally {
    state.sending = false;
    persist();
    renderMessages();
    updateSendBtn();
  }
}

function updateSendBtn() {
  el.sendBtn.disabled = state.sending || !el.input.value.trim();
}

function autosize() {
  el.input.style.height = "auto";
  el.input.style.height = Math.min(el.input.scrollHeight, 200) + "px";
}

function openSettings() { clearSettingsError(); el.settingsModal.classList.remove("hidden"); }
function closeSettings() { el.settingsModal.classList.add("hidden"); }

function bind() {
  el.newChat.addEventListener("click", createChat);
  el.sendBtn.addEventListener("click", sendMessage);
  el.input.addEventListener("input", () => { autosize(); updateSendBtn(); });
  el.input.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey) {
      ev.preventDefault();
      sendMessage();
    }
  });
  el.openSettings.addEventListener("click", openSettings);
  el.saveSettings.addEventListener("click", saveSettings);
  el.providerSwitch.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-provider]");
    if (!btn) return;
    state.settings.provider = btn.dataset.provider;
    renderProviderPanels();
  });
  el.settingsModal.addEventListener("click", (e) => {
    if (e.target.hasAttribute("data-close")) closeSettings();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !el.settingsModal.classList.contains("hidden")) closeSettings();
  });
}

async function pollScene() {
  try {
    const res = await fetch("/api/state");
    const payload = await res.json();
    state.sceneContext = payload.scene_context;
  } catch {}
  setTimeout(pollScene, 3000);
}

async function boot() {
  bind();
  loadChats();
  renderChatList();
  renderTitle();
  renderMessages();
  await loadState();
  updateSendBtn();
  pollScene();
}

boot();
