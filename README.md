# Blender Assistant

A Blender addon that opens a clean, full-size chat companion app in your browser — scene-aware, with support for OpenAI, Anthropic, and Ollama.

The addon itself is thin. The chat UI lives in a proper browser window where it can actually feel polished. Blender stays the bridge: it pushes scene context (active object, selection, mode, etc.) to the companion app so your chats know what you're working on.

---

## Quick Start (under 5 minutes)

### 1. Download the addon

Grab the latest zip from the [Releases page](https://github.com/patmakesapps/blender-ollama/releases) — for example `blender-ollama-v0.7.1-test.zip`.

**Don't unzip it.** Blender installs it as-is.

### 2. Install it in Blender

1. Open Blender.
2. `Edit` → `Preferences` → `Add-ons`.
3. Click `Install...` (top right).
4. Select the zip you downloaded.
5. Tick the checkbox next to **Ollama Chat Assistant** to enable it.

### 3. Open the assistant

1. In the 3D Viewport, press `N` to open the sidebar.
2. Click the `Ollama` tab.
3. Click **Open Assistant**.

This starts a small local server on `http://127.0.0.1:8765` and opens your browser.

### 4. Pick a provider and go

Click **Settings** in the sidebar of the chat app, pick one of:

- **OpenAI** — paste your API key, pick a model (default `gpt-5`), Save.
- **Anthropic** — paste your API key, pick a model, Save.
- **Ollama** — no key needed. Make sure Ollama is running locally and the model name matches one you've pulled (e.g. `ollama pull llama3.2:3b`).

API keys are saved to `~/.blender-ollama/config.json` on your machine — not sent anywhere except the provider you picked.

Close the Settings modal and start chatting.

---

## Provider Setup Details

### OpenAI

1. Get a key at https://platform.openai.com/api-keys
2. Settings → OpenAI → paste key → Save
3. Default model is `gpt-5`; change it to whatever you have access to

### Anthropic

1. Get a key at https://console.anthropic.com/settings/keys
2. Settings → Anthropic → paste key → Save
3. Default model is `claude-sonnet-4-20250514`; change as needed

### Ollama (runs locally, no API key)

1. Install from https://ollama.com/
2. Pull a model:
   ```
   ollama pull llama3.2:3b
   ```
3. Make sure the Ollama app/service is running.
4. Settings → Ollama → set the model name to exactly what you pulled → Save.

---

## Using the App

- **+ New Chat** — start a fresh conversation. Each chat has its own history.
- **Chat list** — click any chat in the sidebar to jump back to it. Hover and click `×` to delete.
- **Enter** sends, **Shift+Enter** adds a newline.
- Chats are stored in your browser's `localStorage` for `http://127.0.0.1:8765` — clearing site data wipes them. They're not synced.

---

## How It Works

1. You click **Open Assistant** in Blender.
2. The addon launches `companion/server.py` (a tiny Python HTTP server) in the background.
3. Your browser opens `http://127.0.0.1:8765`.
4. Every time you click Open Assistant, the addon POSTs the current scene context to the companion.
5. Your messages go to OpenAI / Anthropic / Ollama with that scene context attached as system info.

---

## Troubleshooting

- **"The companion app did not start in time"** — another process is probably on port `8765`. Close it, or restart Blender.
- **"Failed to fetch" errors in the chat** — usually means your API key is missing or wrong, or Ollama isn't running. Open Settings and verify.
- **Ollama says a model isn't available** — `ollama list` to see what you have, then match the name exactly in Settings.
- **Chats disappeared** — you cleared browser site data for `127.0.0.1:8765`. There's no server-side copy.

---

## Notes

- Companion server runs locally on `http://127.0.0.1:8765`. Nothing is exposed to the network.
- API keys stored in `~/.blender-ollama/config.json`.
- Scene context pushed: scene name, active object, selected objects, object count, mode.
- Text-only today. It doesn't execute Blender operations yet.

## Roadmap

- Screenshot capture from Blender into the companion app
- Action buttons that trigger Blender operations from chat
- Persistent chat sessions tied to the current `.blend` file
- File- and asset-aware assistance
