#!/usr/bin/env python3
"""
pylumo-serve - A local OpenAI-compatible HTTP server backed by the Lumo API.

Starts a loopback HTTP server that exposes the pyLumo client through the
OpenAI chat completions API, compatible with any tool that speaks the
OpenAI protocol (opencode, GitHub Copilot BYOK, Cursor, Continue, aider).

Adapted from the `proton lumo serve` design in
https://github.com/major0/proton-utils (Go): same API key format (32 random
bytes, hex-encoded), same endpoints (POST /v1/chat/completions and GET
/v1/models), and the same startup banner posture (the key is printed to
stderr and persisted with mode 0600).

Security notes:
- The API key is never accepted via argv (visible in the process list); it
  is read from the LUMO_API_KEY environment variable or the persisted file.
- The persisted key file is written with mode 0600 under the secure app dir.
"""

import argparse
import json
import os
import secrets
import ssl
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .pylumo import LumoModel, LumoTools, pyLumo

__all__ = [
    "DEFAULT_ADDR",
    "LumoAPIServer",
    "generate_api_key",
    "load_or_generate_api_key",
    "main",
]

DEFAULT_ADDR = "127.0.0.1:8443"
API_KEY_FILE = "lumo-api-key"
API_KEY_BYTES = 32


def generate_api_key() -> str:
    """Generate a new random API key.

    Returns:
        The hex-encoded key (64 chars), matching the format used by
        https://github.com/major0/proton-utils (32 random bytes).

    Example:
        >>> key = generate_api_key()
        >>> len(key), all(c in "0123456789abcdef" for c in key)
        (64, True)
    """
    return secrets.token_hex(API_KEY_BYTES)


def _config_dir() -> str:
    """Return the secure application directory for persisted state.

    Returns:
        Path to the pyLumo application support directory
    """
    return str(pyLumo._get_secure_app_dir())


def load_or_generate_api_key(path: str) -> str:
    """Read the persisted API key, or generate and persist a new one.

    Args:
        path: Path to the API key file

    Returns:
        The API key (64 hex chars when freshly generated)

    Raises:
        OSError: If the key file cannot be written
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            key = f.read().strip()
        if key:
            return key
    except OSError:
        pass
    key = generate_api_key()
    directory = os.path.dirname(path)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(key + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


def resolve_api_key(new_key: bool) -> str:
    """Determine the API key to use.

    Priority: LUMO_API_KEY environment variable (unless --new-api-key),
    then the persisted or freshly generated key file. The key is never
    read from argv, so it stays out of the process list.

    Args:
        new_key: If True, generate and persist a new key regardless

    Returns:
        The API key to require from clients
    """
    if not new_key:
        env = os.environ.get("LUMO_API_KEY")
        if env and env.strip():
            return env.strip()
    return load_or_generate_api_key(os.path.join(_config_dir(), API_KEY_FILE))


def parse_addr(addr: str) -> tuple:
    """Split a listen address into host and port.

    Args:
        addr: Listen address as host:port

    Returns:
        Tuple of (host, port)

    Raises:
        ValueError: If the port is missing or not a number
    """
    host, sep, port = addr.rpartition(":")
    if not sep or not host:
        raise ValueError(f"Invalid listen address: {addr!r}")
    return host, int(port)


def extract_text(content) -> str:
    """Extract plain text from a message content field.

    Accepts a plain string or an OpenAI content-parts list of
    {"type": "text", "text": ...} objects.

    Args:
        content: The message content to extract text from

    Returns:
        The concatenated text
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(part.get("text", ""))
        return "".join(parts)
    return ""


def resolve_model(requested) -> str:
    """Resolve a requested model name to a Lumo model ID.

    Args:
        requested: Model name from the request body (None or "" for auto)

    Returns:
        The LumoModel value to use

    Raises:
        ValueError: If the model is not in the Lumo lineup
    """
    if requested is None or requested == "":
        return LumoModel.AUTO.value
    lowered = requested.lower()
    for model in LumoModel:
        if model.value == lowered:
            return model.value
    raise ValueError(f"Unknown model: {requested!r}")


REASONING_FAST = "none"
REASONING_THINKING = "high"
FAST_EFFORTS = frozenset({"", "auto", "none", "off", "false"})


def resolve_reasoning_effort(effort) -> str:
    """Map a requested reasoning effort to one of Lumo's two reasoning modes.

    Lumo offers Fast mode, which answers as quickly as possible, and
    Thinking mode, which works through a request step by step before
    answering. The API selects between them with the reasoning_effort
    field, where "none" means Fast and any other level means Thinking, so
    low, medium and high are equivalent rather than graded.

    Args:
        effort: Value from the request's reasoning_effort field
            (None or "" for the provider default)

    Returns:
        REASONING_FAST for Fast mode or REASONING_THINKING for Thinking mode

    Example:
        >>> resolve_reasoning_effort("low") == REASONING_THINKING
        True
        >>> resolve_reasoning_effort(None) == REASONING_FAST
        True
    """
    if effort is None or str(effort).strip().lower() in FAST_EFFORTS:
        return REASONING_FAST
    return REASONING_THINKING


def extract_reasoning_effort(body: dict) -> str:
    """Read the reasoning mode an OpenAI-compatible request asks for.

    Accepts the reasoning_effort field and the Anthropic-style thinking
    block some clients send instead. A request that names neither gets
    Fast mode, matching the posture Lumo's own clients default to.

    Args:
        body: The parsed JSON request body

    Returns:
        REASONING_FAST for Fast mode or REASONING_THINKING for Thinking mode
    """
    effort = body.get("reasoning_effort")
    if effort is not None and str(effort).strip():
        return resolve_reasoning_effort(effort)
    thinking = body.get("thinking")
    if isinstance(thinking, dict) and thinking.get("type") not in (None, "", "disabled"):
        return REASONING_THINKING
    return REASONING_FAST


def extract_tool_names(tools) -> list:
    """Extract known Lumo tool names from an OpenAI tools field.

    Accepts built-in tool objects ({"type": "function", "function":
    {"name": ...}}) and bare strings. Names outside Lumo's toolset are
    dropped so the upstream API never rejects the request.

    Args:
        tools: The tools field from the request body

    Returns:
        List of known Lumo tool names
    """
    known = {tool.value for tool in LumoTools}
    names = []
    if isinstance(tools, list):
        for tool in tools:
            if isinstance(tool, str):
                name = tool
            elif isinstance(tool, dict):
                function = tool.get("function")
                if isinstance(function, dict):
                    name = function.get("name", "")
                else:
                    name = tool.get("name", "")
            else:
                continue
            if isinstance(name, str) and name in known and name not in names:
                names.append(name)
    return names


class LumoAPIHandler(BaseHTTPRequestHandler):
    """Request handler exposing the pyLumo client through the OpenAI API."""

    protocol_version = "HTTP/1.1"
    server_version = "pylumo"

    @staticmethod
    def _error(message: str) -> dict:
        return {"error": {"message": message, "type": "invalid_request_error"}}

    def _check_auth(self) -> bool:
        """Validate the Authorization bearer token against the server key."""
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and secrets.compare_digest(
            auth[len("Bearer "):], self.server.api_key
        ):
            return True
        self._send_json(401, {
            "error": {
                "message": "Invalid API key.",
                "type": "invalid_request_error",
                "code": "invalid_api_key",
            },
        })
        return False

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _write_sse(self, data: str) -> None:
        self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _chunk(self, chunk_id: str, model: str, delta: dict,
               finish_reason=None) -> str:
        return json.dumps({
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }],
        })

    def do_GET(self) -> None:
        if self.path == "/v1/models":
            self._handle_models()
        else:
            self._send_json(404, self._error("Unknown endpoint."))

    def do_POST(self) -> None:
        if self.path == "/v1/chat/completions":
            self._handle_chat()
        else:
            self._send_json(404, self._error("Unknown endpoint."))

    def _handle_models(self) -> None:
        if not self._check_auth():
            return
        data = [
            {
                "id": model.value,
                "object": "model",
                "created": 0,
                "owned_by": "proton-lumo",
            }
            for model in LumoModel
        ]
        self._send_json(200, {"object": "list", "data": data})

    def _handle_chat(self) -> None:
        if not self._check_auth():
            return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            self._send_json(400, self._error("Invalid JSON body."))
            return
        if not isinstance(body, dict):
            self._send_json(
                400, self._error("Request body must be a JSON object."))
            return
        try:
            model = resolve_model(body.get("model"))
        except ValueError as e:
            self._send_json(400, self._error(str(e)))
            return
        prompt, history = self._split_messages(body.get("messages"))
        if prompt is None:
            return
        tools = self._resolve_tools(body)
        effort = extract_reasoning_effort(body)
        if body.get("stream"):
            self._stream_chat(model, prompt, history, tools, effort)
        else:
            self._complete_chat(model, prompt, history, tools, effort)

    def _split_messages(self, messages):
        """Split OpenAI messages into history turns and the new prompt."""
        if not isinstance(messages, list) or not messages:
            self._send_json(
                400, self._error("'messages' must be a non-empty list."))
            return None, None
        last = messages[-1]
        if not isinstance(last, dict) or last.get("role") != "user":
            self._send_json(
                400, self._error("Last message must have role 'user'."))
            return None, None
        prompt = extract_text(last.get("content"))
        if not prompt:
            self._send_json(400, self._error("Last message has empty content."))
            return None, None
        history = []
        for turn in messages[:-1]:
            if not isinstance(turn, dict):
                continue
            role = turn.get("role")
            if role in ("user", "assistant", "system"):
                content = extract_text(turn.get("content"))
                if content:
                    history.append({"role": role, "content": content})
        return prompt, history

    def _resolve_tools(self, body: dict):
        client = self.server.client
        if "tools" in body:
            tools = extract_tool_names(body["tools"])
        elif getattr(client, "authenticated_mode", False):
            tools = None  # client default: proton_info
        else:
            tools = []
        if self.server.web_search and "web_search" not in tools:
            if tools is None:
                tools = [
                    LumoTools.PROTON_INFO.value,
                    LumoTools.WEB_SEARCH.value,
                ]
            else:
                tools.append(LumoTools.WEB_SEARCH.value)
        return tools

    def _apply_history(self, history: list) -> None:
        client = self.server.client
        client.clear_conversation_history()
        for turn in history:
            client.add_turn_to_history(turn["role"], turn["content"])

    def _stream_chat(self, model, prompt, history, tools, effort) -> None:
        self._apply_history(history)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        chunk_id = f"chatcmpl-{uuid.uuid4()}"

        def forward(target, text):
            if target == "message" and text:
                self._write_sse(
                    self._chunk(chunk_id, model, {"content": text}))
            elif target == "reasoning" and text:
                self._write_sse(
                    self._chunk(chunk_id, model,
                                {"reasoning_content": text}))

        client = self.server.client
        error_msg = None
        try:
            result = client.send_request(
                prompt,
                tools=tools,
                targets=["message"],
                model=model,
                stream_callback=forward,
                reasoning_effort=effort,
            )
        except Exception as e:
            result = {}
            error_msg = str(e)
        if not isinstance(result, dict) or not result or "_error" in result:
            if error_msg is None and isinstance(result, dict):
                error_msg = (
                    result.get("_error_details") or "Lumo request failed."
                )
            if error_msg is None:
                error_msg = "Lumo request failed."
            self._write_sse(json.dumps({
                "error": {"message": error_msg, "type": "server_error"},
            }))
            self._write_sse("[DONE]")
            return
        self._write_sse(self._chunk(chunk_id, model, {}, "stop"))
        self._write_sse("[DONE]")

    def _complete_chat(self, model, prompt, history, tools, effort) -> None:
        self._apply_history(history)
        client = self.server.client
        try:
            result = client.send_request(
                prompt, tools=tools, targets=["message"], model=model,
                reasoning_effort=effort)
        except Exception as e:
            result = {"_error_details": str(e)}
        if not isinstance(result, dict) or not result or "_error" in result:
            if isinstance(result, dict):
                message = result.get("_error_details") or "Lumo request failed."
            else:
                message = "Lumo request failed."
            self._send_json(502, {
                "error": {"message": message, "type": "server_error"},
            })
            return
        completion = {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": result.get("message", ""),
                },
                "finish_reason": "stop",
            }],
        }
        reasoning = result.get("reasoning")
        if reasoning:
            message = completion["choices"][0]["message"]
            message["reasoning_content"] = reasoning
        usage = result.get("usage")
        if usage:
            try:
                completion["usage"] = json.loads(usage)
            except (json.JSONDecodeError, TypeError):
                pass
        self._send_json(200, completion)


class LumoAPIServer(ThreadingHTTPServer):
    """Threaded HTTP server exposing the pyLumo client via the OpenAI API."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, api_key, client, web_search=False):
        host, port = addr
        super().__init__((host, port), LumoAPIHandler)
        self.api_key = api_key
        self.client = client
        self.web_search = web_search


def _print_banner(scheme, addr, api_key, cert_file) -> None:
    """Write the startup banner to stderr, printing the key once."""
    print("\nProton Lumo server running", file=sys.stderr)
    print(f"  Base URL:  {scheme}://{addr}/v1", file=sys.stderr)
    print(f"  API Key:   {api_key}", file=sys.stderr)
    if cert_file:
        print(f"  TLS Cert:  {cert_file}", file=sys.stderr)
    print("", file=sys.stderr)


def main() -> None:
    """Main entry point for the pylumo-serve command-line interface.

    Starts a local OpenAI-compatible server backed by the pyLumo client.
    The API key is resolved from the environment or the persisted key
    file (never from argv), and the server listens on loopback by default.
    """
    addr_default = os.environ.get("LUMO_ENDPOINT") or DEFAULT_ADDR
    web_default = os.environ.get(
        "LUMO_WEB_SEARCH", "").strip().lower() in ("1", "true")
    parser = argparse.ArgumentParser(
        description=(
            "pylumo-serve - Start a local OpenAI-compatible server "
            "backed by the Lumo API"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--addr",
        default=addr_default,
        help=f"Listen address and port (default: {DEFAULT_ADDR}; "
        "overridable via env LUMO_ENDPOINT)",
    )
    parser.add_argument(
        "--new-api-key",
        action="store_true",
        help="Generate and persist a new API key",
    )
    parser.add_argument("--tls-cert", default="", help="TLS certificate path")
    parser.add_argument("--tls-key", default="", help="TLS private key path")
    parser.add_argument(
        "--web-search",
        action="store_true",
        default=web_default,
        help="Enable Lumo's web_search tool by default "
        "(overridable via env LUMO_WEB_SEARCH)",
    )
    args = parser.parse_args()

    try:
        addr = parse_addr(args.addr)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)

    if bool(args.tls_cert) != bool(args.tls_key):
        print(
            "Error: --tls-cert and --tls-key must be provided together.",
            file=sys.stderr,
        )
        sys.exit(2)

    api_key = resolve_api_key(args.new_api_key)

    client = pyLumo(quiet_mode=True)
    session_path = os.path.expanduser("~/.pylumo_session.json")
    if os.path.exists(session_path):
        try:
            client.load_session(session_path)
        except Exception as e:
            print(
                f"Warning: could not load saved session: {e}; "
                "using guest mode.",
                file=sys.stderr,
            )

    server = LumoAPIServer(
        addr, api_key, client, web_search=args.web_search)
    scheme = "https" if args.tls_cert else "http"
    if scheme == "http" and addr[0] not in (
        "127.0.0.1", "::1", "localhost"
    ):
        print(
            "Warning: serving plain HTTP off loopback; the API key "
            "travels unencrypted. Use --tls-cert/--tls-key.",
            file=sys.stderr,
        )
    if args.tls_cert:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(args.tls_cert, args.tls_key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    _print_banner(scheme, args.addr, api_key, args.tls_cert)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.", file=sys.stderr)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
