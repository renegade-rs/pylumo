#!/usr/bin/env python3
"""Tests for the pyLumo local OpenAI-compatible server (serve module).

Tests cover:
- API key generation, persistence, and resolution
- Endpoint authentication (401 without a valid bearer key)
- GET /v1/models model listing
- POST /v1/chat/completions (streaming and non-streaming)
- Request validation (bad JSON, unknown model, message roles)
"""

import json
import os
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from unittest import mock

from pylumo.serve import (
    LumoAPIServer,
    extract_text,
    extract_tool_names,
    generate_api_key,
    load_or_generate_api_key,
    parse_addr,
    resolve_api_key,
    resolve_model,
)

TEST_KEY = "0" * 64


class FakeClient:
    """Stand-in for pyLumo that records calls and returns a canned reply."""

    def __init__(self, reply="Hello from Lumo."):
        self.reply = reply
        self.calls = []
        self.history = []
        self.authenticated_mode = False

    def clear_conversation_history(self):
        self.history = []

    def add_turn_to_history(self, role, content, tool_call=None,
                            tool_result=None):
        self.history.append({"role": role, "content": content})

    def send_request(self, prompt, tools=None, targets=None, model=None,
                     stream_callback=None):
        self.calls.append({
            "prompt": prompt,
            "tools": tools,
            "targets": targets,
            "model": model,
        })
        if stream_callback:
            stream_callback("message", self.reply)
        return {"message": self.reply}


class ServeTestCase(unittest.TestCase):
    """Base class that runs a real server on an ephemeral loopback port."""

    def make_server(self, client=None, api_key=TEST_KEY, web_search=False):
        self.server = LumoAPIServer(
            ("127.0.0.1", 0),
            api_key=api_key,
            client=client or FakeClient(),
            web_search=web_search,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True)
        self.thread.start()

        def stop():
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=10)

        self.addCleanup(stop)
        self.port = self.server.server_address[1]

    def request(self, method, path, body=None, token=TEST_KEY):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=10)
        self.addCleanup(conn.close)
        headers = {}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        payload = None
        if body is not None:
            payload = body if isinstance(body, (bytes, str)) else json.dumps(
                body)
            payload = payload.encode("utf-8") if isinstance(
                payload, str) else payload
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        data = response.read()
        return response, data


class TestServeAPIKey(unittest.TestCase):
    """API key generation, persistence, and resolution."""

    def test_generate_api_key_format(self):
        key = generate_api_key()
        self.assertEqual(len(key), 64)
        self.assertEqual(int(key, 16) >= 0, True)
        self.assertEqual(key, key.lower())

    def test_load_or_generate_creates_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sub", "lumo-api-key")
            key = load_or_generate_api_key(path)
            self.assertEqual(len(key), 64)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            with open(path, "r", encoding="utf-8") as f:
                self.assertEqual(f.read().strip(), key)
            self.assertEqual(load_or_generate_api_key(path), key)

    def test_load_existing_key(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "lumo-api-key")
            with open(path, "w", encoding="utf-8") as f:
                f.write("abc123\n")
            self.assertEqual(load_or_generate_api_key(path), "abc123")

    def test_resolve_api_key_env(self):
        with mock.patch.dict(os.environ, {"LUMO_API_KEY": " envkey "},
                             clear=False):
            self.assertEqual(resolve_api_key(False), "envkey")

    def test_resolve_api_key_new_ignores_env(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "lumo-api-key")
            with open(path, "w", encoding="utf-8") as f:
                f.write("persisted\n")
            with mock.patch(
                "pylumo.serve._config_dir", return_value=d,
            ), mock.patch.dict(os.environ, {"LUMO_API_KEY": "envkey"}):
                self.assertEqual(resolve_api_key(True), "persisted")

    def test_parse_addr(self):
        self.assertEqual(parse_addr("127.0.0.1:8443"), ("127.0.0.1", 8443))
        with self.assertRaises(ValueError):
            parse_addr("127.0.0.1")


class TestServeHelpers(unittest.TestCase):
    """Message content, model, and tool mapping helpers."""

    def test_extract_text_string_and_parts(self):
        self.assertEqual(extract_text("hi"), "hi")
        parts = [
            {"type": "text", "text": "a"},
            {"type": "image_url", "image_url": {}},
            {"type": "text", "text": "b"},
        ]
        self.assertEqual(extract_text(parts), "ab")

    def test_resolve_model(self):
        self.assertEqual(resolve_model("lumo-lite"), "lumo-lite")
        self.assertEqual(resolve_model("LUMO-MAX"), "lumo-max")
        self.assertEqual(resolve_model(None), "auto")
        self.assertEqual(resolve_model(""), "auto")
        with self.assertRaises(ValueError):
            resolve_model("gpt-99")

    def test_extract_tool_names(self):
        tools = [
            {"type": "function", "function": {"name": "web_search"}},
            {"type": "function", "function": {"name": "browser"}},
            "proton_info",
        ]
        self.assertEqual(
            extract_tool_names(tools), ["web_search", "proton_info"])


class TestServeEndpoints(ServeTestCase):
    """Authentication and endpoint behavior over a live loopback server."""

    def setUp(self):
        self.client = FakeClient()
        self.make_server(client=self.client)

    def test_models_requires_auth(self):
        response, data = self.request("GET", "/v1/models", token=None)
        self.assertEqual(response.status, 401)
        self.assertEqual(json.loads(data)["error"]["code"], "invalid_api_key")

    def test_models_wrong_key(self):
        response, data = self.request("GET", "/v1/models", token="wrong")
        self.assertEqual(response.status, 401)

    def test_models_lists_lumo_models(self):
        response, data = self.request("GET", "/v1/models")
        self.assertEqual(response.status, 200)
        payload = json.loads(data)
        self.assertEqual(payload["object"], "list")
        ids = [m["id"] for m in payload["data"]]
        self.assertIn("lumo-lite", ids)
        self.assertIn("lumo-max", ids)
        self.assertIn("auto", ids)

    def test_chat_requires_auth(self):
        response, _ = self.request(
            "POST", "/v1/chat/completions",
            body={"messages": [{"role": "user", "content": "hi"}]},
            token=None,
        )
        self.assertEqual(response.status, 401)

    def test_chat_non_streaming(self):
        body = {
            "model": "lumo-lite",
            "messages": [
                {"role": "system", "content": "Sys"},
                {"role": "user", "content": "Earlier"},
                {"role": "assistant", "content": "Prior reply"},
                {"role": "user", "content": "Latest question"},
            ],
        }
        response, data = self.request(
            "POST", "/v1/chat/completions", body=body)
        self.assertEqual(response.status, 200)
        payload = json.loads(data)
        self.assertEqual(payload["object"], "chat.completion")
        self.assertEqual(
            payload["choices"][0]["message"]["content"], "Hello from Lumo.")
        call = self.client.calls[0]
        self.assertEqual(call["prompt"], "Latest question")
        self.assertEqual(call["model"], "lumo-lite")
        self.assertEqual(self.client.history, [
            {"role": "system", "content": "Sys"},
            {"role": "user", "content": "Earlier"},
            {"role": "assistant", "content": "Prior reply"},
        ])

    def test_chat_streaming(self):
        body = {
            "model": "auto",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
        }
        response, data = self.request(
            "POST", "/v1/chat/completions", body=body)
        self.assertEqual(response.status, 200)
        self.assertEqual(
            response.getheader("Content-Type"), "text/event-stream")
        text = data.decode("utf-8")
        self.assertIn("data: ", text)
        self.assertTrue(text.endswith("data: [DONE]\n\n"))
        events = [
            line[len("data: "):] for line in text.splitlines()
            if line.startswith("data: ") and line != "data: [DONE]"
        ]
        chunks = [json.loads(event) for event in events]
        self.assertEqual(
            chunks[0]["object"], "chat.completion.chunk")
        content = "".join(
            c["choices"][0]["delta"].get("content", "") for c in chunks)
        self.assertEqual(content, "Hello from Lumo.")
        self.assertEqual(
            chunks[-1]["choices"][0]["finish_reason"], "stop")

    def test_chat_content_parts(self):
        body = {
            "messages": [{
                "role": "user",
                "content": [{"type": "text", "text": "Part one. "},
                            {"type": "text", "text": "Part two."}],
            }],
        }
        response, data = self.request(
            "POST", "/v1/chat/completions", body=body)
        self.assertEqual(response.status, 200)
        self.assertEqual(
            self.client.calls[0]["prompt"], "Part one. Part two.")

    def test_chat_bad_json(self):
        response, data = self.request(
            "POST", "/v1/chat/completions", body="{not json")
        self.assertEqual(response.status, 400)

    def test_chat_unknown_model(self):
        body = {
            "model": "gpt-99",
            "messages": [{"role": "user", "content": "hi"}],
        }
        response, data = self.request(
            "POST", "/v1/chat/completions", body=body)
        self.assertEqual(response.status, 400)

    def test_chat_last_message_must_be_user(self):
        body = {
            "messages": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ],
        }
        response, data = self.request(
            "POST", "/v1/chat/completions", body=body)
        self.assertEqual(response.status, 400)

    def test_chat_empty_messages(self):
        response, data = self.request(
            "POST", "/v1/chat/completions", body={"messages": []})
        self.assertEqual(response.status, 400)

    def test_chat_tools_filtered(self):
        body = {
            "messages": [{"role": "user", "content": "hi"}],
            "tools": [
                {"type": "function", "function": {"name": "web_search"}},
                {"type": "function", "function": {"name": "browser"}},
            ],
        }
        response, data = self.request(
            "POST", "/v1/chat/completions", body=body)
        self.assertEqual(response.status, 200)
        self.assertEqual(self.client.calls[0]["tools"], ["web_search"])

    def test_unknown_endpoint_404(self):
        response, _ = self.request("GET", "/v1/nope")
        self.assertEqual(response.status, 404)


class TestServeWebSearchFlag(ServeTestCase):
    """The --web-search server flag enables the tool by default."""

    def setUp(self):
        self.client = FakeClient()
        self.make_server(client=self.client, web_search=True)

    def test_web_search_appended(self):
        body = {"messages": [{"role": "user", "content": "hi"}]}
        response, data = self.request(
            "POST", "/v1/chat/completions", body=body)
        self.assertEqual(response.status, 200)
        self.assertIn("web_search", self.client.calls[0]["tools"])
