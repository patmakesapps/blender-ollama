import json
import os
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error, request


HOST = "127.0.0.1"
PORT = 8765
STATIC_DIR = Path(__file__).resolve().parent / "static"
CONFIG_DIR = Path.home() / ".blender-ollama"
CONFIG_PATH = CONFIG_DIR / "config.json"
OPENAI_API_URL = "https://api.openai.com/v1/responses"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
OLLAMA_API_URL = "http://127.0.0.1:11434/api/chat"

DEFAULT_SETTINGS = {
    "provider": "openai",
    "openai_model": "gpt-5",
    "anthropic_model": "claude-sonnet-4-20250514",
    "ollama_model": "ministral-3:14b-cloud",
    "openai_api_key": "",
    "anthropic_api_key": "",
}
STATE = {
    "scene_context": {
        "scene_name": "Unknown",
        "active_object": "None",
        "selected_objects": [],
        "object_count": 0,
        "mode": "OBJECT",
    },
    "settings": {},
}


def load_settings():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    settings = dict(DEFAULT_SETTINGS)

    if CONFIG_PATH.exists():
        try:
            settings.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass

    if os.getenv("OPENAI_API_KEY"):
        settings["openai_api_key"] = os.getenv("OPENAI_API_KEY")
    if os.getenv("ANTHROPIC_API_KEY"):
        settings["anthropic_api_key"] = os.getenv("ANTHROPIC_API_KEY")

    return settings


def save_settings(settings):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def masked_settings():
    settings = dict(STATE["settings"])
    settings["openai_api_key_configured"] = bool(settings.get("openai_api_key"))
    settings["anthropic_api_key_configured"] = bool(settings.get("anthropic_api_key"))
    settings["openai_api_key"] = ""
    settings["anthropic_api_key"] = ""
    return settings


def build_prompt_messages(chat_messages):
    messages = []
    for message in chat_messages:
        role = message.get("role", "user")
        content = message.get("content", "").strip()
        if not content:
            continue
        messages.append({"role": role, "content": content})
    return messages


def scene_context_block():
    return json.dumps(STATE["scene_context"], indent=2)


def openai_chat(chat_messages, model_name):
    api_key = STATE["settings"].get("openai_api_key", "").strip()
    if not api_key:
        raise RuntimeError("OpenAI is selected, but no API key is configured.")

    payload = {
        "model": model_name,
        "instructions": (
            "You are a premium Blender copilot inside a companion app. "
            "Be concise, practical, and visually structured. "
            "Prefer numbered steps for procedural guidance. "
            "Avoid markdown emphasis like **bold** unless absolutely necessary. "
            "Current Blender scene context:\n"
            f"{scene_context_block()}"
        ),
        "input": build_prompt_messages(chat_messages),
    }

    req = request.Request(
        OPENAI_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=90) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI request failed: {details}") from exc
    except error.URLError as exc:
        raise RuntimeError("Could not reach the OpenAI API.") from exc

    text = parsed.get("output_text")
    if text:
        return text

    for item in parsed.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            text = content.get("text")
            if text:
                return text

    raise RuntimeError("OpenAI returned an unexpected response payload.")


def anthropic_chat(chat_messages, model_name):
    api_key = STATE["settings"].get("anthropic_api_key", "").strip()
    if not api_key:
        raise RuntimeError("Anthropic is selected, but no API key is configured.")

    payload = {
        "model": model_name,
        "max_tokens": 1200,
        "system": (
            "You are a premium Blender copilot inside a companion app. "
            "Be concise, practical, and visually structured. "
            "Prefer numbered steps for procedural guidance. "
            "Avoid markdown emphasis like **bold** unless absolutely necessary. "
            "Current Blender scene context:\n"
            f"{scene_context_block()}"
        ),
        "messages": build_prompt_messages(chat_messages),
    }

    req = request.Request(
        ANTHROPIC_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=90) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Anthropic request failed: {details}") from exc
    except error.URLError as exc:
        raise RuntimeError("Could not reach the Anthropic API.") from exc

    for content in parsed.get("content", []):
        text = content.get("text")
        if text:
            return text

    raise RuntimeError("Anthropic returned an unexpected response payload.")


def ollama_chat(chat_messages, model_name):
    latest_messages = build_prompt_messages(chat_messages)
    if latest_messages:
        latest_messages[-1]["content"] = (
            "Blender scene context:\n"
            f"{scene_context_block()}\n\n"
            f"User request:\n{latest_messages[-1]['content']}"
        )

    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a Blender expert helping inside a premium companion app. "
                    "Prefer numbered steps and clean plain text."
                ),
            },
            *latest_messages,
        ],
        "stream": False,
    }

    req = request.Request(
        OLLAMA_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=90) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama request failed: {details}") from exc
    except error.URLError as exc:
        raise RuntimeError("Could not reach Ollama at http://127.0.0.1:11434.") from exc

    message = parsed.get("message", {})
    content = message.get("content")
    if content:
        return content

    raise RuntimeError("Ollama returned an unexpected response payload.")


class CompanionHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, format, *args):
        return

    def do_GET(self):
        if self.path == "/api/state":
            return self.respond_json(
                {
                    "scene_context": STATE["scene_context"],
                    "settings": masked_settings(),
                }
            )
        return super().do_GET()

    def do_POST(self):
        try:
            if self.path == "/api/scene":
                payload = self.read_json()
                STATE["scene_context"] = payload.get("scene_context", STATE["scene_context"])
                return self.respond_json({"ok": True})

            if self.path == "/api/settings":
                payload = self.read_json()
                settings = dict(STATE["settings"])
                for key in ("provider", "openai_model", "anthropic_model", "ollama_model"):
                    if key in payload:
                        settings[key] = payload[key]
                if payload.get("openai_api_key"):
                    settings["openai_api_key"] = payload["openai_api_key"]
                if payload.get("anthropic_api_key"):
                    settings["anthropic_api_key"] = payload["anthropic_api_key"]
                STATE["settings"] = settings
                save_settings(settings)
                return self.respond_json({"ok": True, "settings": masked_settings()})

            if self.path == "/api/chat":
                payload = self.read_json()
                provider = payload.get("provider") or STATE["settings"]["provider"]
                model_name = payload.get("model")
                chat_messages = payload.get("messages", [])

                if provider == "openai":
                    model_name = model_name or STATE["settings"]["openai_model"]
                    content = openai_chat(chat_messages, model_name)
                elif provider == "anthropic":
                    model_name = model_name or STATE["settings"]["anthropic_model"]
                    content = anthropic_chat(chat_messages, model_name)
                else:
                    model_name = model_name or STATE["settings"]["ollama_model"]
                    content = ollama_chat(chat_messages, model_name)

                return self.respond_json({"content": content})

            self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")
        except RuntimeError as exc:
            return self.respond_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            return self.respond_json({"error": f"Server error: {exc}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def read_json(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length else b"{}"
        return json.loads(raw_body.decode("utf-8") or "{}")

    def respond_json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    STATE["settings"] = load_settings()
    server = ThreadingHTTPServer((HOST, PORT), CompanionHandler)
    print(f"Blender companion app running at http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
