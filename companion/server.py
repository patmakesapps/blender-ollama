import json
import os
import sqlite3
import time
import uuid
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error, request


HOST = "127.0.0.1"
PORT = 8767
STATIC_DIR = Path(__file__).resolve().parent / "static"
CONFIG_DIR = Path.home() / ".blender-ollama"
CONFIG_PATH = CONFIG_DIR / "config.json"
DB_PATH = CONFIG_DIR / "chats.db"

OPENAI_API_URL = "https://api.openai.com/v1/responses"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
OLLAMA_API_URL = "http://127.0.0.1:11434/api/chat"
BLENDER_EXEC_URL = "http://127.0.0.1:8766/exec"

TOOL_NAME = "run_blender_python"
TOOL_DESCRIPTION = (
    "Execute Python code inside the running Blender session. "
    "`bpy` is already imported. Use this for Blender actions."
)
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "code": {
            "type": "string",
            "description": "Python code to run inside Blender. `bpy` is already imported.",
        },
        "explanation": {
            "type": "string",
            "description": "One short sentence explaining what the code will do.",
        },
    },
    "required": ["code", "explanation"],
}
SYSTEM_PROMPT = (
    "You are a Blender copilot inside a companion chat app. "
    "Be concise and practical. "
    "You have access to the `run_blender_python` tool - use it whenever "
    "the user asks for anything you can do with the Blender Python API "
    "(modeling, modifiers, materials, animation, scripting, scene edits). "
    "The user will review the code and approve it before it runs, so write "
    "code that directly does the requested job."
)

DEFAULT_SETTINGS = {
    "provider": "openai",
    "openai_model": "gpt-5",
    "anthropic_model": "claude-sonnet-4-20250514",
    "ollama_model": "llama3.1:8b",
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


def save_settings_to_disk(settings):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def masked_settings():
    settings = dict(STATE["settings"])
    settings["openai_api_key_configured"] = bool(settings.get("openai_api_key"))
    settings["anthropic_api_key_configured"] = bool(settings.get("anthropic_api_key"))
    settings["openai_api_key"] = ""
    settings["anthropic_api_key"] = ""
    return settings


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT,
                images TEXT,
                tool_calls TEXT,
                tool_call_id TEXT,
                tool_name TEXT,
                tool_approved INTEGER,
                tool_output TEXT,
                created_at INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_messages_chat_created
                ON messages(chat_id, created_at);
            """
        )


def now_ms():
    return int(time.time() * 1000)


def new_id():
    return uuid.uuid4().hex[:16]


def create_chat(title="New Chat"):
    chat_id = new_id()
    ts = now_ms()
    with db() as conn:
        conn.execute(
            "INSERT INTO chats(id, title, created_at, updated_at) VALUES(?, ?, ?, ?)",
            (chat_id, title, ts, ts),
        )
    return chat_id


def list_chats_db():
    with db() as conn:
        rows = conn.execute(
            "SELECT id, title, created_at, updated_at FROM chats ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def delete_chat_db(chat_id):
    with db() as conn:
        conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))


def rename_chat_db(chat_id, title):
    with db() as conn:
        conn.execute(
            "UPDATE chats SET title = ?, updated_at = ? WHERE id = ?",
            (title, now_ms(), chat_id),
        )


def auto_title_if_first_message(chat_id, text):
    with db() as conn:
        row = conn.execute("SELECT title FROM chats WHERE id = ?", (chat_id,)).fetchone()
        count = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE chat_id = ? AND role = 'user'",
            (chat_id,),
        ).fetchone()[0]
    if row and row["title"] == "New Chat" and count == 0:
        snippet = (text or "New Chat").strip().splitlines()[0][:60]
        if len(text or "") > 60:
            snippet += "..."
        rename_chat_db(chat_id, snippet or "New Chat")


def insert_message(
    chat_id,
    role,
    content=None,
    images=None,
    tool_calls=None,
    tool_call_id=None,
    tool_name=None,
    tool_approved=None,
    tool_output=None,
):
    message_id = new_id()
    ts = now_ms()
    with db() as conn:
        conn.execute(
            """
            INSERT INTO messages(
                id, chat_id, role, content, images, tool_calls,
                tool_call_id, tool_name, tool_approved, tool_output, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                chat_id,
                role,
                content,
                json.dumps(images) if images else None,
                json.dumps(tool_calls) if tool_calls else None,
                tool_call_id,
                tool_name,
                None if tool_approved is None else (1 if tool_approved else 0),
                tool_output,
                ts,
            ),
        )
        conn.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (ts, chat_id))
    return message_id


def get_messages(chat_id):
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at",
            (chat_id,),
        ).fetchall()

    messages = []
    for row in rows:
        message = dict(row)
        if message.get("images"):
            try:
                message["images"] = json.loads(message["images"])
            except Exception:
                message["images"] = []
        if message.get("tool_calls"):
            try:
                message["tool_calls"] = json.loads(message["tool_calls"])
            except Exception:
                message["tool_calls"] = []
        if message.get("tool_approved") is not None:
            message["tool_approved"] = bool(message["tool_approved"])
        messages.append(message)
    return messages


def has_pending_tool_calls(messages):
    for message in reversed(messages):
        if message["role"] == "assistant" and message.get("tool_calls"):
            resolved_ids = {
                tool_message["tool_call_id"]
                for tool_message in messages
                if tool_message["role"] == "tool" and tool_message.get("tool_call_id")
            }
            return any(tool_call["id"] not in resolved_ids for tool_call in message["tool_calls"])
        if message["role"] == "assistant":
            return False
    return False


def current_model():
    settings = STATE["settings"]
    provider = settings.get("provider", "openai")
    return {
        "openai": settings.get("openai_model"),
        "anthropic": settings.get("anthropic_model"),
        "ollama": settings.get("ollama_model"),
    }.get(provider)


def scene_context_block():
    return json.dumps(STATE["scene_context"], indent=2)


def system_text():
    return SYSTEM_PROMPT + "\n\nCurrent Blender scene context:\n" + scene_context_block()


def strip_data_url(image_url):
    if image_url.startswith("data:"):
        header, _, data = image_url.partition(",")
        media_type = header[5:].split(";")[0] or "image/png"
        return media_type, data
    return None, image_url


def openai_build_input(messages):
    items = []
    for message in messages:
        role = message["role"]
        if role == "user":
            content = []
            if message.get("content"):
                content.append({"type": "input_text", "text": message["content"]})
            for image in message.get("images") or []:
                content.append({"type": "input_image", "image_url": image})
            items.append({"role": "user", "content": content})
        elif role == "assistant":
            if message.get("content"):
                items.append(
                    {
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": message["content"]}],
                    }
                )
            for tool_call in message.get("tool_calls") or []:
                items.append(
                    {
                        "type": "function_call",
                        "call_id": tool_call["id"],
                        "name": tool_call["name"],
                        "arguments": tool_call["arguments"],
                    }
                )
        elif role == "tool":
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": message["tool_call_id"],
                    "output": message.get("tool_output") or "",
                }
            )
    return items


def openai_call(messages, model):
    api_key = STATE["settings"].get("openai_api_key", "").strip()
    if not api_key:
        raise RuntimeError("OpenAI API key is not set. Open Settings and add one.")

    payload = {
        "model": model,
        "instructions": system_text(),
        "input": openai_build_input(messages),
        "tools": [
            {
                "type": "function",
                "name": TOOL_NAME,
                "description": TOOL_DESCRIPTION,
                "parameters": TOOL_SCHEMA,
            }
        ],
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
        with request.urlopen(req, timeout=180) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI request failed: {details}") from exc
    except error.URLError as exc:
        raise RuntimeError("Could not reach the OpenAI API.") from exc

    text_parts = []
    tool_calls = []
    for item in parsed.get("output", []):
        item_type = item.get("type")
        if item_type == "message":
            for content in item.get("content", []):
                if content.get("type") in ("output_text", "text"):
                    text = content.get("text")
                    if text:
                        text_parts.append(text)
        elif item_type == "function_call":
            tool_calls.append(
                {
                    "id": item.get("call_id") or new_id(),
                    "name": item.get("name") or TOOL_NAME,
                    "arguments": item.get("arguments") or "{}",
                }
            )

    return {
        "content": ("\n".join(text_parts).strip() or None),
        "tool_calls": tool_calls or None,
    }


def anthropic_build_messages(messages):
    built = []
    for message in messages:
        role = message["role"]
        if role == "user":
            content = []
            if message.get("content"):
                content.append({"type": "text", "text": message["content"]})
            for image in message.get("images") or []:
                media_type, data = strip_data_url(image)
                content.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type or "image/png",
                            "data": data,
                        },
                    }
                )
            built.append({"role": "user", "content": content})
        elif role == "assistant":
            content = []
            if message.get("content"):
                content.append({"type": "text", "text": message["content"]})
            for tool_call in message.get("tool_calls") or []:
                try:
                    arguments = json.loads(tool_call.get("arguments") or "{}")
                except Exception:
                    arguments = {}
                content.append(
                    {
                        "type": "tool_use",
                        "id": tool_call["id"],
                        "name": tool_call["name"],
                        "input": arguments,
                    }
                )
            if not content:
                content = [{"type": "text", "text": ""}]
            built.append({"role": "assistant", "content": content})
        elif role == "tool":
            built.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": message["tool_call_id"],
                            "content": message.get("tool_output") or "",
                        }
                    ],
                }
            )
    return built


def anthropic_call(messages, model):
    api_key = STATE["settings"].get("anthropic_api_key", "").strip()
    if not api_key:
        raise RuntimeError("Anthropic API key is not set. Open Settings and add one.")

    payload = {
        "model": model,
        "max_tokens": 4096,
        "system": system_text(),
        "messages": anthropic_build_messages(messages),
        "tools": [
            {
                "name": TOOL_NAME,
                "description": TOOL_DESCRIPTION,
                "input_schema": TOOL_SCHEMA,
            }
        ],
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
        with request.urlopen(req, timeout=180) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Anthropic request failed: {details}") from exc
    except error.URLError as exc:
        raise RuntimeError("Could not reach the Anthropic API.") from exc

    text_parts = []
    tool_calls = []
    for block in parsed.get("content", []):
        block_type = block.get("type")
        if block_type == "text":
            text_parts.append(block.get("text", ""))
        elif block_type == "tool_use":
            tool_calls.append(
                {
                    "id": block.get("id") or new_id(),
                    "name": block.get("name") or TOOL_NAME,
                    "arguments": json.dumps(block.get("input") or {}),
                }
            )

    return {
        "content": ("\n".join(text_parts).strip() or None),
        "tool_calls": tool_calls or None,
    }


def ollama_build_messages(messages):
    built = [{"role": "system", "content": system_text()}]
    for message in messages:
        role = message["role"]
        if role == "user":
            built_message = {"role": "user", "content": message.get("content") or ""}
            if message.get("images"):
                built_message["images"] = [
                    strip_data_url(image)[1] for image in message["images"]
                ]
            built.append(built_message)
        elif role == "assistant":
            built_message = {"role": "assistant", "content": message.get("content") or ""}
            if message.get("tool_calls"):
                tool_calls = []
                for tool_call in message["tool_calls"]:
                    try:
                        arguments = json.loads(tool_call.get("arguments") or "{}")
                    except Exception:
                        arguments = {}
                    tool_calls.append(
                        {
                            "function": {
                                "name": tool_call["name"],
                                "arguments": arguments,
                            }
                        }
                    )
                built_message["tool_calls"] = tool_calls
            built.append(built_message)
        elif role == "tool":
            built.append(
                {
                    "role": "tool",
                    "content": message.get("tool_output") or "",
                    "tool_name": message.get("tool_name") or TOOL_NAME,
                }
            )
    return built


def ollama_call(messages, model):
    payload = {
        "model": model,
        "messages": ollama_build_messages(messages),
        "stream": False,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": TOOL_NAME,
                    "description": TOOL_DESCRIPTION,
                    "parameters": TOOL_SCHEMA,
                },
            }
        ],
    }
    req = request.Request(
        OLLAMA_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=300) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama request failed: {details}") from exc
    except error.URLError as exc:
        raise RuntimeError("Could not reach Ollama at http://127.0.0.1:11434.") from exc

    message = parsed.get("message") or {}
    text = (message.get("content") or "").strip() or None
    tool_calls = []
    for tool_call in message.get("tool_calls") or []:
        function = tool_call.get("function") or {}
        arguments = function.get("arguments")
        if isinstance(arguments, dict):
            arguments = json.dumps(arguments)
        elif not isinstance(arguments, str):
            arguments = "{}"
        tool_calls.append(
            {
                "id": tool_call.get("id") or new_id(),
                "name": function.get("name") or TOOL_NAME,
                "arguments": arguments,
            }
        )

    return {"content": text, "tool_calls": tool_calls or None}


def call_llm(messages, provider, model):
    if provider == "openai":
        return openai_call(messages, model)
    if provider == "anthropic":
        return anthropic_call(messages, model)
    return ollama_call(messages, model)


def exec_in_blender(code):
    payload = json.dumps({"code": code}).encode("utf-8")
    req = request.Request(
        BLENDER_EXEC_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.URLError:
        return {
            "ok": False,
            "error": (
                "Could not reach the Blender executor at 127.0.0.1:8766. "
                "Make sure Blender is open with the addon enabled."
            ),
        }
    except Exception as exc:
        return {"ok": False, "error": f"Executor error: {exc}"}


def format_tool_output(result):
    parts = ["Execution succeeded." if result.get("ok") else "Execution failed."]
    if result.get("output"):
        parts.append("stdout/stderr:\n" + result["output"])
    if result.get("error"):
        parts.append("error:\n" + result["error"])
    return "\n\n".join(parts)


def run_llm_round(chat_id):
    messages = get_messages(chat_id)
    provider = STATE["settings"].get("provider", "openai")
    model = current_model()
    if not model:
        raise RuntimeError("No model configured for the current provider.")
    result = call_llm(messages, provider, model)
    return insert_message(
        chat_id,
        role="assistant",
        content=result.get("content"),
        tool_calls=result.get("tool_calls"),
    )


class CompanionHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, format, *args):
        return

    def do_GET(self):
        if self.path == "/api/state":
            return self._json(
                {
                    "scene_context": STATE["scene_context"],
                    "settings": masked_settings(),
                }
            )
        if self.path == "/api/chats":
            return self._json({"chats": list_chats_db()})
        if self.path.startswith("/api/chats/") and self.path.endswith("/messages"):
            chat_id = self.path.split("/")[3]
            return self._json({"messages": get_messages(chat_id)})
        return super().do_GET()

    def do_POST(self):
        try:
            if self.path == "/api/scene":
                body = self._read_json()
                STATE["scene_context"] = body.get("scene_context", STATE["scene_context"])
                return self._json({"ok": True})

            if self.path == "/api/settings":
                body = self._read_json()
                settings = dict(STATE["settings"])
                for key in ("provider", "openai_model", "anthropic_model", "ollama_model"):
                    if key in body:
                        settings[key] = body[key]
                if body.get("openai_api_key"):
                    settings["openai_api_key"] = body["openai_api_key"]
                if body.get("anthropic_api_key"):
                    settings["anthropic_api_key"] = body["anthropic_api_key"]

                provider = settings.get("provider")
                if provider == "openai" and not settings.get("openai_api_key", "").strip():
                    return self._json(
                        {"error": "OpenAI requires an API key. Add one in Settings or switch providers."},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                if provider == "anthropic" and not settings.get("anthropic_api_key", "").strip():
                    return self._json(
                        {"error": "Anthropic requires an API key. Add one in Settings or switch providers."},
                        status=HTTPStatus.BAD_REQUEST,
                    )

                STATE["settings"] = settings
                save_settings_to_disk(settings)
                return self._json({"ok": True, "settings": masked_settings()})

            if self.path == "/api/chats":
                body = self._read_json()
                chat_id = create_chat(body.get("title") or "New Chat")
                return self._json({"chat": {"id": chat_id, "title": "New Chat"}})

            if self.path.startswith("/api/chats/") and self.path.endswith("/send"):
                chat_id = self.path.split("/")[3]
                body = self._read_json()
                text = (body.get("text") or "").strip()
                images = body.get("images") or []
                if not text and not images:
                    return self._json(
                        {"error": "Empty message."},
                        status=HTTPStatus.BAD_REQUEST,
                    )

                auto_title_if_first_message(chat_id, text)
                insert_message(chat_id, role="user", content=text, images=images)
                run_llm_round(chat_id)
                return self._json({"messages": get_messages(chat_id)})

            if self.path.startswith("/api/chats/") and self.path.endswith("/resolve"):
                chat_id = self.path.split("/")[3]
                body = self._read_json()
                resolution_map = {
                    item.get("id"): bool(item.get("approved"))
                    for item in (body.get("resolutions") or [])
                    if item.get("id")
                }

                messages = get_messages(chat_id)
                pending = None
                for message in reversed(messages):
                    if message["role"] == "assistant" and message.get("tool_calls"):
                        resolved_ids = {
                            tool_message["tool_call_id"]
                            for tool_message in messages
                            if tool_message["role"] == "tool" and tool_message.get("tool_call_id")
                        }
                        if any(tool_call["id"] not in resolved_ids for tool_call in message["tool_calls"]):
                            pending = message
                        break

                if not pending:
                    return self._json(
                        {"error": "No pending tool calls."},
                        status=HTTPStatus.BAD_REQUEST,
                    )

                for tool_call in pending["tool_calls"]:
                    if tool_call["id"] not in resolution_map:
                        continue

                    approved = resolution_map[tool_call["id"]]
                    if approved:
                        try:
                            arguments = json.loads(tool_call.get("arguments") or "{}")
                        except Exception:
                            arguments = {}
                        result = exec_in_blender(arguments.get("code") or "")
                        output = format_tool_output(result)
                    else:
                        output = (
                            "The user declined to run this code. "
                            "Do not retry the same action - explain what you would have done, "
                            "or suggest an alternative approach."
                        )

                    insert_message(
                        chat_id,
                        role="tool",
                        tool_call_id=tool_call["id"],
                        tool_name=tool_call["name"],
                        tool_approved=approved,
                        tool_output=output,
                    )

                messages = get_messages(chat_id)
                if not has_pending_tool_calls(messages):
                    run_llm_round(chat_id)
                return self._json({"messages": get_messages(chat_id)})

            self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")
        except RuntimeError as exc:
            return self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            return self._json(
                {"error": f"Server error: {exc}"},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def do_DELETE(self):
        if self.path.startswith("/api/chats/"):
            parts = self.path.split("/")
            if len(parts) == 4:
                delete_chat_db(parts[3])
                return self._json({"ok": True})
        self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")

    def do_PATCH(self):
        if self.path.startswith("/api/chats/"):
            parts = self.path.split("/")
            if len(parts) == 4:
                body = self._read_json()
                rename_chat_db(parts[3], (body.get("title") or "").strip() or "New Chat")
                return self._json({"ok": True})
        self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def _json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    init_db()
    STATE["settings"] = load_settings()
    server = ThreadingHTTPServer((HOST, PORT), CompanionHandler)
    print(f"Blender companion app running at http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
