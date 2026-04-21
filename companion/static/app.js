const state = {
  chats: [],
  activeId: null,
  messages: [],
  settings: null,
  sending: false,
  pendingImages: [],
};

const el = {
  chatList: document.getElementById("chat-list"),
  newChat: document.getElementById("new-chat"),
  chatTitle: document.getElementById("chat-title"),
  messages: document.getElementById("message-list"),
  input: document.getElementById("composer-input"),
  sendBtn: document.getElementById("send-button"),
  attachBtn: document.getElementById("attach-btn"),
  fileInput: document.getElementById("file-input"),
  imagePreview: document.getElementById("image-preview"),
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

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `${res.status} ${res.statusText}`);
  return data;
}

async function boot() {
  bind();
  await loadSettings();
  await loadChats();
  if (!state.chats.length) {
    await createChat();
  } else {
    state.activeId = state.chats[0].id;
    await loadMessages();
    renderAll();
  }
  updateSendBtn();
}

function bind() {
  el.newChat.addEventListener("click", createChat);
  el.sendBtn.addEventListener("click", sendMessage);
  el.attachBtn.addEventListener("click", () => el.fileInput.click());
  el.fileInput.addEventListener("change", handleFilePick);
  el.openSettings.addEventListener("click", openSettings);
  el.saveSettings.addEventListener("click", saveSettings);

  el.input.addEventListener("input", () => {
    autosize();
    updateSendBtn();
  });
  el.input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  });
  el.input.addEventListener("paste", handlePaste);

  el.providerSwitch.addEventListener("click", (event) => {
    const button = event.target.closest("[data-provider]");
    if (!button || !state.settings) return;
    state.settings.provider = button.dataset.provider;
    renderProviderPanels();
    renderModelPill();
  });

  el.settingsModal.addEventListener("click", (event) => {
    if (event.target.hasAttribute("data-close")) closeSettings();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !el.settingsModal.classList.contains("hidden")) {
      closeSettings();
    }
  });
}

async function loadSettings() {
  try {
    const payload = await api("/api/state");
    state.settings = payload.settings;
    renderSettings();
    renderModelPill();
  } catch {
    state.settings = {
      provider: "openai",
      openai_model: "gpt-5",
      anthropic_model: "claude-sonnet-4-20250514",
      ollama_model: "llama3.1:8b",
    };
  }
}

async function loadChats() {
  const payload = await api("/api/chats");
  state.chats = payload.chats || [];
}

async function loadMessages() {
  if (!state.activeId) {
    state.messages = [];
    return;
  }
  const payload = await api(`/api/chats/${state.activeId}/messages`);
  state.messages = payload.messages || [];
}

async function createChat() {
  const payload = await api("/api/chats", { method: "POST", body: "{}" });
  state.activeId = payload.chat.id;
  await loadChats();
  await loadMessages();
  renderAll();
  el.input.focus();
}

async function deleteChat(id) {
  await api(`/api/chats/${id}`, { method: "DELETE" });
  if (state.activeId === id) state.activeId = null;
  await loadChats();
  if (!state.chats.length) {
    await createChat();
    return;
  }
  if (!state.activeId) state.activeId = state.chats[0].id;
  await loadMessages();
  renderAll();
}

async function selectChat(id) {
  if (state.activeId === id) return;
  state.activeId = id;
  await loadMessages();
  renderAll();
}

async function sendMessage() {
  if (state.sending) return;
  const text = el.input.value.trim();
  const images = state.pendingImages.slice();
  if (!text && !images.length) return;

  state.sending = true;
  el.input.value = "";
  state.pendingImages = [];
  autosize();
  renderImagePreview();
  updateSendBtn();

  state.messages.push({
    id: `tmp-user-${Date.now()}`,
    role: "user",
    content: text,
    images,
  });
  state.messages.push({
    id: `tmp-pending-${Date.now()}`,
    role: "assistant",
    content: "Thinking...",
    _pending: true,
  });
  renderMessages();

  try {
    const payload = await api(`/api/chats/${state.activeId}/send`, {
      method: "POST",
      body: JSON.stringify({ text, images }),
    });
    state.messages = payload.messages || [];
    await loadChats();
    renderChatList();
    renderTitle();
  } catch (error) {
    state.messages = state.messages.filter((message) => !message._pending);
    state.messages.push({
      id: `err-${Date.now()}`,
      role: "assistant",
      content: `Error: ${error.message}`,
      _error: true,
    });
  } finally {
    state.sending = false;
    renderMessages();
    updateSendBtn();
  }
}

async function resolveToolCalls(resolutions) {
  if (state.sending) return;
  state.sending = true;
  updateSendBtn();

  state.messages.push({
    id: `tmp-tool-${Date.now()}`,
    role: "assistant",
    content: "Running...",
    _pending: true,
  });
  renderMessages();

  try {
    const payload = await api(`/api/chats/${state.activeId}/resolve`, {
      method: "POST",
      body: JSON.stringify({ resolutions }),
    });
    state.messages = payload.messages || [];
  } catch (error) {
    state.messages = state.messages.filter((message) => !message._pending);
    state.messages.push({
      id: `err-${Date.now()}`,
      role: "assistant",
      content: `Error: ${error.message}`,
      _error: true,
    });
  } finally {
    state.sending = false;
    renderMessages();
    updateSendBtn();
  }
}

function renderAll() {
  renderChatList();
  renderTitle();
  renderMessages();
}

function renderChatList() {
  el.chatList.innerHTML = "";
  for (const chat of state.chats) {
    const item = document.createElement("button");
    item.className = `chat-item${chat.id === state.activeId ? " active" : ""}`;
    item.innerHTML =
      '<span class="chat-item-title"></span><span class="chat-item-close" aria-label="Delete">x</span>';
    item.querySelector(".chat-item-title").textContent = chat.title || "New Chat";
    item.addEventListener("click", (event) => {
      if (event.target.classList.contains("chat-item-close")) {
        event.stopPropagation();
        void deleteChat(chat.id);
        return;
      }
      void selectChat(chat.id);
    });
    el.chatList.appendChild(item);
  }
}

function renderTitle() {
  const chat = state.chats.find((item) => item.id === state.activeId);
  el.chatTitle.textContent = chat?.title || "New Chat";
}

function renderMessages() {
  el.messages.innerHTML = "";

  const toolResultsByCallId = new Map();
  for (const message of state.messages) {
    if (message.role === "tool" && message.tool_call_id) {
      toolResultsByCallId.set(message.tool_call_id, message);
    }
  }

  const visibleMessages = state.messages.filter((message) => message.role !== "tool");
  if (!visibleMessages.length) {
    const empty = document.createElement("div");
    empty.className = "empty-hint";
    empty.innerHTML =
      "<h3>How can I help with Blender?</h3><p>Ask about modeling, modifiers, materials, animation, scripting, images, or have me run Python for you.</p>";
    el.messages.appendChild(empty);
    return;
  }

  for (const message of visibleMessages) {
    const wrap = document.createElement("div");
    wrap.className = `msg ${message.role}${message._pending ? " pending" : ""}${message._error ? " error" : ""}`;

    if (message.images?.length) {
      const imageRow = document.createElement("div");
      imageRow.className = "msg-images";
      for (const src of message.images) {
        const img = document.createElement("img");
        img.src = src;
        img.alt = "User attachment";
        imageRow.appendChild(img);
      }
      wrap.appendChild(imageRow);
    }

    if (message.content) {
      const bubble = document.createElement("div");
      bubble.className = "msg-bubble";
      bubble.innerHTML = renderMarkdown(message.content);
      wrap.appendChild(bubble);
    }

    if (message.role === "assistant" && message.tool_calls?.length) {
      for (const toolCall of message.tool_calls) {
        wrap.appendChild(renderToolCard(toolCall, toolResultsByCallId.get(toolCall.id)));
      }
    }

    el.messages.appendChild(wrap);
  }

  el.messages.scrollTop = el.messages.scrollHeight;
}

function renderToolCard(toolCall, resolved) {
  const card = document.createElement("div");
  card.className = "tool-card";

  let args = {};
  try {
    args = JSON.parse(toolCall.arguments || "{}");
  } catch {}

  const head = document.createElement("div");
  head.className = "tool-card-head";
  head.innerHTML =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg><span class="tool-card-title">Run in Blender</span>';

  const explanation = document.createElement("p");
  explanation.className = "tool-card-explanation";
  explanation.textContent = args.explanation || "Run Python in Blender";

  const pre = document.createElement("pre");
  pre.className = "tool-card-code";
  const code = document.createElement("code");
  code.textContent = args.code || "";
  pre.appendChild(code);

  card.appendChild(head);
  card.appendChild(explanation);
  card.appendChild(pre);

  if (!resolved) {
    const actions = document.createElement("div");
    actions.className = "tool-card-actions";

    const approve = document.createElement("button");
    approve.className = "primary-btn small";
    approve.textContent = "Approve and run";
    approve.addEventListener("click", () => void resolveToolCalls([{ id: toolCall.id, approved: true }]));

    const reject = document.createElement("button");
    reject.className = "ghost-btn small";
    reject.textContent = "Reject";
    reject.addEventListener("click", () => void resolveToolCalls([{ id: toolCall.id, approved: false }]));

    actions.appendChild(approve);
    actions.appendChild(reject);
    card.appendChild(actions);
  } else {
    const status = document.createElement("div");
    const ok = resolved.tool_approved && !/Execution failed/.test(resolved.tool_output || "");
    status.className = `tool-card-status ${ok ? "ok" : "fail"}`;
    status.textContent = resolved.tool_approved
      ? ok
        ? "Ran successfully"
        : "Ran with errors"
      : "Declined";
    card.appendChild(status);

    if (resolved.tool_output) {
      const output = document.createElement("pre");
      output.className = "tool-card-output";
      output.textContent = resolved.tool_output;
      card.appendChild(output);
    }
  }

  return card;
}

function renderMarkdown(text) {
  const escape = (value) =>
    value.replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[char]));

  let out = "";
  const parts = text.split(/(```[\s\S]*?```)/g);
  for (const part of parts) {
    if (part.startsWith("```") && part.endsWith("```")) {
      const body = part.slice(3, -3).replace(/^[a-zA-Z0-9_-]*\n/, "");
      out += `<pre><code>${escape(body)}</code></pre>`;
    } else {
      let segment = escape(part);
      segment = segment.replace(/`([^`\n]+)`/g, "<code>$1</code>");
      segment = segment.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
      out += segment;
    }
  }
  return out;
}

function renderSettings() {
  const settings = state.settings || {};
  state.settings.provider = settings.provider || "openai";
  el.openaiModel.value = settings.openai_model || "gpt-5";
  el.anthropicModel.value = settings.anthropic_model || "claude-sonnet-4-20250514";
  el.ollamaModel.value = settings.ollama_model || "llama3.1:8b";
  el.openaiKey.placeholder = settings.openai_api_key_configured
    ? "API key saved locally"
    : "Paste an API key to enable OpenAI";
  el.anthropicKey.placeholder = settings.anthropic_api_key_configured
    ? "API key saved locally"
    : "Paste an API key to enable Anthropic";
  renderProviderPanels();
}

function renderProviderPanels() {
  const provider = state.settings?.provider || "openai";
  document.querySelectorAll(".provider-chip").forEach((button) => {
    button.classList.toggle("active", button.dataset.provider === provider);
  });
  document.querySelectorAll(".provider-panel").forEach((panel) => {
    panel.classList.toggle("hidden", panel.dataset.panel !== provider);
  });
}

function renderModelPill() {
  const settings = state.settings || {};
  const provider = settings.provider || "openai";
  const model =
    provider === "openai"
      ? settings.openai_model
      : provider === "anthropic"
        ? settings.anthropic_model
        : settings.ollama_model;
  el.modelPillText.textContent = model || provider;
}

function showSettingsError(message) {
  el.settingsError.textContent = message;
  el.settingsError.classList.remove("hidden");
}

function clearSettingsError() {
  el.settingsError.classList.add("hidden");
  el.settingsError.textContent = "";
}

async function saveSettings() {
  clearSettingsError();

  const provider = state.settings.provider;
  const settings = state.settings || {};
  if (provider === "openai") {
    const hasKey = el.openaiKey.value.trim() || settings.openai_api_key_configured;
    if (!hasKey) {
      showSettingsError("OpenAI requires an API key. Paste one above or switch providers.");
      return;
    }
  }
  if (provider === "anthropic") {
    const hasKey = el.anthropicKey.value.trim() || settings.anthropic_api_key_configured;
    if (!hasKey) {
      showSettingsError("Anthropic requires an API key. Paste one above or switch providers.");
      return;
    }
  }

  try {
    const payload = await api("/api/settings", {
      method: "POST",
      body: JSON.stringify({
        provider,
        openai_model: el.openaiModel.value.trim(),
        anthropic_model: el.anthropicModel.value.trim(),
        ollama_model: el.ollamaModel.value.trim(),
        openai_api_key: el.openaiKey.value.trim(),
        anthropic_api_key: el.anthropicKey.value.trim(),
      }),
    });
    state.settings = payload.settings;
    el.openaiKey.value = "";
    el.anthropicKey.value = "";
    renderSettings();
    renderModelPill();
    closeSettings();
  } catch (error) {
    showSettingsError(error.message || "Could not save settings");
  }
}

function openSettings() {
  clearSettingsError();
  el.settingsModal.classList.remove("hidden");
}

function closeSettings() {
  el.settingsModal.classList.add("hidden");
}

function autosize() {
  el.input.style.height = "auto";
  el.input.style.height = `${Math.min(el.input.scrollHeight, 200)}px`;
}

function updateSendBtn() {
  const hasContent = Boolean(el.input.value.trim() || state.pendingImages.length);
  el.sendBtn.disabled = state.sending || !hasContent;
}

function handlePaste(event) {
  const items = event.clipboardData?.items || [];
  const images = [];
  for (const item of items) {
    if (item.kind === "file" && item.type.startsWith("image/")) {
      const file = item.getAsFile();
      if (file) images.push(file);
    }
  }
  if (images.length) {
    event.preventDefault();
    images.forEach(addImageFile);
  }
}

function handleFilePick(event) {
  const files = Array.from(event.target.files || []);
  files.forEach(addImageFile);
  event.target.value = "";
}

function addImageFile(file) {
  const reader = new FileReader();
  reader.onload = () => {
    state.pendingImages.push(reader.result);
    renderImagePreview();
    updateSendBtn();
  };
  reader.readAsDataURL(file);
}

function renderImagePreview() {
  el.imagePreview.innerHTML = "";
  if (!state.pendingImages.length) {
    el.imagePreview.classList.add("hidden");
    return;
  }

  el.imagePreview.classList.remove("hidden");
  state.pendingImages.forEach((src, index) => {
    const thumb = document.createElement("div");
    thumb.className = "thumb";

    const img = document.createElement("img");
    img.src = src;
    img.alt = "Pending attachment";

    const remove = document.createElement("button");
    remove.type = "button";
    remove.setAttribute("aria-label", "Remove image");
    remove.textContent = "x";
    remove.addEventListener("click", () => {
      state.pendingImages.splice(index, 1);
      renderImagePreview();
      updateSendBtn();
    });

    thumb.appendChild(img);
    thumb.appendChild(remove);
    el.imagePreview.appendChild(thumb);
  });
}

boot();
