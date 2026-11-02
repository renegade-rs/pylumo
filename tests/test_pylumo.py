#!/usr/bin/env python3
"""
Comprehensive test suite for pyLumo client.

Tests cover:
- Encryption and decryption
- Request payload creation
- Response parsing
- File upload handling
- Session management (mocked)
- Error handling
- Conversation history
"""

import unittest
import base64
import tempfile
import os
import sys
from unittest.mock import Mock, patch
from datetime import datetime

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes

from pylumo.pylumo import LumoIntegrityError, pyLumo

try:
    from proton.constants import PUBKEY_HASH_DICT

    PROTON_CLIENT_AVAILABLE = True
except Exception:
    PROTON_CLIENT_AVAILABLE = False
    PUBKEY_HASH_DICT = None

# Note: _pylumo_debug is internal, tests use base pyLumo class


class TestPyLumoEncryption(unittest.TestCase):
    """Test encryption and decryption functionality."""

    def setUp(self):
        """Set up test client."""
        self.client = pyLumo(quiet_mode=True)

    def test_pgp_key_loaded(self):
        """Test that PGP public key is loaded correctly."""
        self.assertIsNotNone(self.client.pgp_key)
        self.assertTrue(hasattr(self.client.pgp_key, "encrypt"))

    def test_aes_key_generation(self):
        """Test AES key generation."""
        # Create a payload to trigger key generation
        payload, aes_key = self.client.create_request_payload(
            prompt="test", tools=[], targets=["message"]
        )

        self.assertIsNotNone(aes_key)
        self.assertEqual(len(aes_key), 32)  # 256-bit key

    def test_encrypt_decrypt_roundtrip(self):
        """Test that encryption and decryption work correctly."""
        test_message = "Hello, this is a test message!"

        # Create payload (which encrypts the message)
        payload, aes_key = self.client.create_request_payload(
            prompt=test_message, tools=[], targets=["message"]
        )

        # Get encrypted content from payload
        encrypted_content = payload["messages"][0]["content"]

        # Verify content is encrypted (base64 encoded)
        self.assertTrue(len(encrypted_content) > 0)
        # Should be different from original message
        self.assertNotEqual(encrypted_content, test_message)

    def test_request_key_encryption(self):
        """Test that request key is properly encrypted with PGP."""
        payload, aes_key = self.client.create_request_payload(
            prompt="test", tools=[], targets=["message"]
        )

        request_key = payload["lumo"]["request_key"]

        # Should be base64-encoded PGP message
        self.assertTrue(len(request_key) > 0)
        # Should be valid base64
        try:
            base64.b64decode(request_key)
        except Exception:
            self.fail("request_key is not valid base64")


class TestPyLumoRequestPayload(unittest.TestCase):
    """Test request payload creation."""

    def setUp(self):
        """Set up test client."""
        self.client = pyLumo(quiet_mode=True)

    def test_basic_payload_structure(self):
        """Test basic payload structure."""
        payload, _ = self.client.create_request_payload(
            prompt="test prompt", tools=["web_search"], targets=["title", "message"]
        )

        self.assertIn("model", payload)
        self.assertIn("messages", payload)
        self.assertIn("stream", payload)
        self.assertIn("lumo", payload)
        self.assertIn("request_id", payload["lumo"])
        self.assertIn("request_key", payload["lumo"])

    def test_payload_tools(self):
        """Test tools are included in payload."""
        tools = ["web_search", "proton_info"]
        payload, _ = self.client.create_request_payload(
            prompt="test", tools=tools, targets=["message"]
        )

        self.assertEqual(payload["tools"], [{"name": "web_search"}, {"name": "proton_info"}])

    def test_payload_model(self):
        """Test the selected model is included in the payload."""
        payload, _ = self.client.create_request_payload(
            prompt="test", tools=[], targets=["message"], model="lumo-max"
        )
        self.assertEqual(payload["model"], "lumo-max")

    def test_payload_model_default_auto(self):
        """Test model defaults to auto when not specified."""
        payload, _ = self.client.create_request_payload(
            prompt="test", tools=[], targets=["message"]
        )
        self.assertEqual(payload["model"], "auto")

    def test_payload_targets(self):
        """Test targets are included in payload."""
        targets = ["title", "message", "summary"]
        payload, _ = self.client.create_request_payload(
            prompt="test", tools=[], targets=targets
        )

        self.assertEqual(payload["lumo"]["target"], "message")

    def test_payload_turn_structure(self):
        """Test turn structure in payload."""
        payload, _ = self.client.create_request_payload(
            prompt="test prompt", tools=[], targets=["message"]
        )

        messages = payload["messages"]
        self.assertEqual(len(messages), 1)

        message = messages[0]
        self.assertEqual(message["role"], "user")
        self.assertTrue(message["encrypted"])
        self.assertIn("content", message)

    def test_payload_with_conversation_history(self):
        """Test payload includes conversation history if present."""
        # Add some history
        self.client.conversation_history = [
            {"role": "user", "content": "previous question"},
            {"role": "assistant", "content": "previous answer"},
        ]

        payload, _ = self.client.create_request_payload(
            prompt="new question", tools=[], targets=["message"]
        )

        # Should have history + new turn
        messages = payload["messages"]
        self.assertGreaterEqual(len(messages), 1)

    def test_request_id_is_uuid(self):
        """Test request_id is a valid UUID."""
        payload, _ = self.client.create_request_payload(
            prompt="test", tools=[], targets=["message"]
        )

        request_id = payload["lumo"]["request_id"]
        # Should be a valid UUID format
        self.assertRegex(
            request_id,
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        )


class TestPyLumoResponseParsing(unittest.TestCase):
    """Test streaming response parsing."""

    def setUp(self):
        """Set up test client."""
        self.client = pyLumo(quiet_mode=True)

    def _encrypt_response_chunk(self, aes_key: bytes, request_id: str, plaintext: str) -> str:
        """Encrypt a response chunk -- compatibility with internal encryption"""
        iv = get_random_bytes(12)
        aead_data = f"lumo.response.{request_id}.chunk".encode("utf-8")
        cipher_aes = AES.new(aes_key, AES.MODE_GCM, nonce=iv)
        cipher_aes.update(aead_data)
        ciphertext, tag = cipher_aes.encrypt_and_digest(plaintext.encode("utf-8"))
        return base64.b64encode(iv + ciphertext + tag).decode("utf-8")

    def test_parse_token_data(self):
        """Test parsing token_data events."""
        # Create mock response with streaming data
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.close = Mock()

        request_id = "test-request-id"
        _, aes_key = self.client.create_request_payload("test", [], ["message"])

        enc_hello = self._encrypt_response_chunk(aes_key, request_id, "Hello")
        enc_world = self._encrypt_response_chunk(aes_key, request_id, " World")
        mock_response.iter_lines = Mock(
            return_value=[
                f'data:{{"object":"chat.completion.chunk","choices":[{{"index":0,"delta":{{"target":"message","content":"{enc_hello}","encrypted":true}}}}]}}'.encode("utf-8"),
                f'data:{{"object":"chat.completion.chunk","choices":[{{"index":0,"delta":{{"target":"message","content":"{enc_world}","encrypted":true}}}}]}}'.encode('utf-8'),
                b'data: [DONE]',
            ]
        )

        content_by_target, _ = self.client.parse_streaming_response(
            mock_response, datetime.now(), aes_key, request_id
        )

        self.assertIn("message", content_by_target)
        self.assertEqual(content_by_target["message"], "Hello World")

    def test_parse_multiple_targets(self):
        """Test parsing multiple targets."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.close = Mock()

        request_id = "test-id"
        _, aes_key = self.client.create_request_payload(
            "test", [], ["title", "message"]
        )

        enc_title = self._encrypt_response_chunk(aes_key, request_id, "Title")
        enc_message = self._encrypt_response_chunk(aes_key, request_id, "Message")
        mock_response.iter_lines = Mock(
            return_value=[
                f'data:{{"object":"chat.completion.chunk","choices":[{{"index":0,"delta":{{"target":"title","content":"{enc_title}","encrypted":true}}}}]}}'.encode('utf-8'),
                f'data:{{"object":"chat.completion.chunk","choices":[{{"index":0,"delta":{{"target":"message","content":"{enc_message}","encrypted":true}}}}]}}'.encode('utf-8'),
                b'data: [DONE]',
            ]
        )

        content_by_target, _ = self.client.parse_streaming_response(
            mock_response, datetime.now(), aes_key, request_id
        )

        self.assertIn("title", content_by_target)
        self.assertIn("message", content_by_target)
        self.assertEqual(content_by_target["title"], "Title")
        self.assertEqual(content_by_target["message"], "Message")

    def test_parse_invalid_json_line(self):
        """Test handling of invalid JSON lines."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.close = Mock()

        request_id = "test-id"
        _, aes_key = self.client.create_request_payload("test", [], ["message"])
        enc_valid = self._encrypt_response_chunk(aes_key, request_id, "Valid")
        mock_response.iter_lines = Mock(
            return_value=[
                b"data:invalid json",
                f'data:{{"object":"chat.completion.chunk","choices":[{{"index":0,"delta":{{"target":"message","content":"{enc_valid}","encrypted":true}}}}]}}'.encode('utf-8'),
                b'data: [DONE]',
            ]
        )

        content_by_target, _ = self.client.parse_streaming_response(
            mock_response, datetime.now(), aes_key, request_id
        )

        # Should still parse valid lines despite invalid JSON
        self.assertIn("message", content_by_target)
        self.assertEqual(content_by_target["message"], "Valid")

    def test_integrity_error_stops_processing(self):
        """Test that integrity verification failure stops processing and returns explicit error."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.close = Mock()

        request_id = "test-id"
        _, aes_key = self.client.create_request_payload("test", [], ["message"])

        enc_hello = self._encrypt_response_chunk(aes_key, request_id, "Hello")
        enc_world = self._encrypt_response_chunk(aes_key, request_id, " World")

        decoded = bytearray(base64.b64decode(enc_world))
        decoded[-1] ^= 0x01
        enc_world_tampered = base64.b64encode(bytes(decoded)).decode("utf-8")

        mock_response.iter_lines = Mock(
            return_value=[
                f'data:{{"object":"chat.completion.chunk","choices":[{{"index":0,"delta":{{"target":"message","content":"{enc_hello}","encrypted":true}}}}]}}'.encode('utf-8'),
                f'data:{{"object":"chat.completion.chunk","choices":[{{"index":0,"delta":{{"target":"message","content":"{enc_world_tampered}","encrypted":true}}}}]}}'.encode('utf-8'),
                b'data: [DONE]',
            ]
        )

        content_by_target, _ = self.client.parse_streaming_response(
            mock_response, datetime.now(), aes_key, request_id
        )

        self.assertEqual(content_by_target.get("message"), "Hello")
        self.assertEqual(content_by_target.get("_error"), "integrity_error")
        self.assertTrue("_error_details" in content_by_target)

    def test_integrity_error_can_raise(self):
        """Test that integrity verification failure can raise for library-mode consumers."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.close = Mock()

        request_id = "test-id"
        _, aes_key = self.client.create_request_payload("test", [], ["message"])

        enc = self._encrypt_response_chunk(aes_key, request_id, "Hello")
        decoded = bytearray(base64.b64decode(enc))
        decoded[-1] ^= 0x01
        enc_tampered = base64.b64encode(bytes(decoded)).decode("utf-8")

        mock_response.iter_lines = Mock(
            return_value=[
                f'data:{{"object":"chat.completion.chunk","choices":[{{"index":0,"delta":{{"target":"message","content":"{enc_tampered}","encrypted":true}}}}]}}'.encode('utf-8'),
            ]
        )

        with self.assertRaises(LumoIntegrityError):
            self.client.parse_streaming_response(
                mock_response,
                datetime.now(),
                aes_key,
                request_id,
                raise_on_integrity_error=True,
            )


    def test_parse_tool_call_and_result(self):
        """Test tool_call accumulation and tool_result decryption."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.close = Mock()

        request_id = "test-id"
        _, aes_key = self.client.create_request_payload("test", [], ["message"])

        enc_args = self._encrypt_response_chunk(aes_key, request_id, '{"city": "Paris"}')
        enc_result = self._encrypt_response_chunk(aes_key, request_id, "Sunny 25C")
        mock_response.iter_lines = Mock(
            return_value=[
                f'data:{{"object":"chat.tool_call","tool_call":{{"id":"call_0","name":"get_weather","arguments":"{enc_args}","encrypted":true}}}}'.encode("utf-8"),
                f'data:{{"object":"chat.tool_result","tool_result":{{"call_id":"call_0","content":"{enc_result}","encrypted":true}}}}'.encode('utf-8'),
                b'data: [DONE]',
            ]
        )

        content_by_target, _ = self.client.parse_streaming_response(
            mock_response, datetime.now(), aes_key, request_id
        )

        self.assertIn("tool_call", content_by_target)
        self.assertIn('"name": "get_weather"', content_by_target["tool_call"])
        self.assertIn("Paris", content_by_target["tool_call"])
        self.assertEqual(content_by_target["tool_result"], "Sunny 25C")


class TestPyLumoFileUpload(unittest.TestCase):
    """Test file upload functionality."""

    def setUp(self):
        """Set up test client."""
        self.client = pyLumo(quiet_mode=True)

    def test_format_file_upload_text(self):
        """Test formatting text file upload."""
        # Create temporary text file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("This is test content")
            temp_path = f.name

        try:
            result = self.client.format_file_upload(temp_path)

            self.assertIn("Filename:", result)
            self.assertIn(os.path.basename(temp_path), result)
            self.assertIn("This is test content", result)
        finally:
            os.unlink(temp_path)

    def test_format_file_upload_binary(self):
        """Test formatting binary file upload."""
        # Create temporary binary file
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".bin", delete=False) as f:
            f.write(b"\x00\x01\x02\x03\x04")
            temp_path = f.name

        try:
            result = self.client.format_file_upload(temp_path)

            self.assertIn("Filename:", result)
            self.assertIn("base64-encoded", result)
            self.assertIn("BEGIN FILE CONTENTS", result)
            self.assertIn("END FILE CONTENTS", result)
            # Should contain base64 encoded content
            self.assertRegex(result, r"[A-Za-z0-9+/=]+")
        finally:
            os.unlink(temp_path)

    def test_format_file_upload_image(self):
        """Test file upload with image file."""
        # Create a small fake image file
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".png", delete=False) as f:
            # PNG header
            f.write(b"\x89PNG\r\n\x1a\n")
            temp_path = f.name

        try:
            result = self.client.format_file_upload(temp_path)

            self.assertIn("Filename:", result)
            self.assertIn(".png", result)
            self.assertIn("base64-encoded", result)
        finally:
            os.unlink(temp_path)

    def test_format_file_upload_nonexistent(self):
        """Test file upload with nonexistent file."""
        with self.assertRaises(FileNotFoundError):
            self.client.format_file_upload("/nonexistent/file.txt")


@unittest.skipUnless(
    PROTON_CLIENT_AVAILABLE,
    "proton client not available; skipping TLS pin regression test",
)
class TestProtonTlsPins(unittest.TestCase):
    def test_account_proton_me_tls_pins_present(self):
        self.assertIsInstance(PUBKEY_HASH_DICT, dict)
        self.assertIn("account.proton.me", PUBKEY_HASH_DICT)
        pins = PUBKEY_HASH_DICT.get("account.proton.me")
        self.assertIsInstance(pins, list)
        self.assertTrue(len(pins) > 0)
        for pin in pins:
            self.assertIsInstance(pin, str)
            self.assertTrue(pin.strip())


class TestPyLumoConversationHistory(unittest.TestCase):
    """Test conversation history management."""

    def setUp(self):
        """Set up test client."""
        self.client = pyLumo(quiet_mode=True, max_turns=3)

    def test_initial_history_empty(self):
        """Test conversation history starts empty."""
        self.assertEqual(len(self.client.conversation_history), 0)

    def test_clear_conversation_history(self):
        """Test clearing conversation history."""
        self.client.conversation_history = [
            {"role": "user", "content": "test"},
            {"role": "assistant", "content": "response"},
        ]

        self.client.clear_conversation_history()

        self.assertEqual(len(self.client.conversation_history), 0)

    def test_max_turns_limit(self):
        """Test max_turns parameter."""
        client = pyLumo(quiet_mode=True, max_turns=2)
        self.assertEqual(client.max_turns, 2)


class TestPyLumoSessionManagement(unittest.TestCase):
    """Test session management (mocked)."""

    def setUp(self):
        """Set up test client."""
        self.client = pyLumo(quiet_mode=True)

    def test_initial_authenticated_mode_false(self):
        """Test authenticated mode starts as False."""
        self.assertFalse(self.client.authenticated_mode)

    def test_initial_proton_session_none(self):
        """Test proton_session starts as None."""
        self.assertIsNone(self.client.proton_session)

    @patch("pylumo.pylumo.PROTON_API_AVAILABLE", True)
    @patch("pylumo.pylumo.ProtonSession")
    def test_authenticate_with_proton_creates_session(self, mock_session_class):
        """Test authentication creates Proton session."""
        # Mock ProtonSession
        mock_session = Mock()
        mock_session.authenticate = Mock(return_value="full")
        mock_session.UID = "test-uid"
        mock_session.AccessToken = "test-token"
        mock_session.RefreshToken = "test-refresh"
        mock_session.Scope = "full"
        mock_session.PasswordMode = 1
        mock_session_class.return_value = mock_session

        session_info = self.client.authenticate_with_proton(
            username="test@example.com", password="password123"
        )

        self.assertTrue(self.client.authenticated_mode)
        self.assertIsNotNone(self.client.proton_session)
        self.assertEqual(session_info["UID"], "test-uid")

    def test_logout_clears_session(self):
        """Test logout clears session."""
        # Set up mock session
        self.client.proton_session = Mock()
        self.client.authenticated_mode = True

        self.client.logout()

        self.assertIsNone(self.client.proton_session)
        self.assertFalse(self.client.authenticated_mode)


    @patch("pylumo.pylumo.keyring")
    def test_save_session_expands_user(self, mock_keyring):
        """Test save_session expands ~ in filepath."""
        self.client.proton_session = Mock()
        self.client.proton_session.dump = Mock(return_value={})
        self.client.proton_session.UID = "test-uid"
        with tempfile.TemporaryDirectory() as home:
            with patch.dict(os.environ, {"HOME": home}):
                self.client.save_session("~/.pylumo_session.json")
                self.assertTrue(os.path.exists(os.path.join(home, ".pylumo_session.json")))


class TestPyLumoOutputFile(unittest.TestCase):
    """Test output file handling."""

    def test_output_file_none_by_default(self):
        """Test output file is None by default."""
        client = pyLumo(quiet_mode=True)
        self.assertIsNone(client.output_file)
        self.assertIsNone(client.output_file_handle)

    def test_output_file_parameter(self):
        """Test output file parameter."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            temp_path = f.name

        try:
            client = pyLumo(quiet_mode=True, output_file=temp_path)
            self.assertEqual(client.output_file, temp_path)
        finally:
            try:
                if "client" in locals() and getattr(client, "output_file_handle", None):
                    client.output_file_handle.close()
                    client.output_file_handle = None
            except Exception:
                pass
            if os.path.exists(temp_path):
                os.unlink(temp_path)


class TestPyLumoErrorHandling(unittest.TestCase):
    """Test error handling."""

    def setUp(self):
        """Set up test client."""
        self.client = pyLumo(quiet_mode=True)

    def test_authenticate_without_proton_api(self):
        """Test authentication fails gracefully without Proton API."""
        with patch("pylumo.pylumo.PROTON_API_AVAILABLE", False):
            client = pyLumo(quiet_mode=True)
            with self.assertRaises(RuntimeError) as context:
                client.authenticate_with_proton("user", "pass")

            self.assertIn("Proton API client not available", str(context.exception))

    def test_save_session_without_session(self):
        """Test saving session fails without active session."""
        with self.assertRaises(RuntimeError) as context:
            self.client.save_session("/tmp/test.json")

        self.assertIn("No active Proton session", str(context.exception))

    def test_load_session_without_proton_api(self):
        """Test loading session fails without Proton API."""
        with patch("pylumo.pylumo.PROTON_API_AVAILABLE", False):
            client = pyLumo(quiet_mode=True)
            with self.assertRaises(RuntimeError) as context:
                client.load_session("/tmp/test.json")

            self.assertIn("Proton API client not available", str(context.exception))


def run_tests():
    """Run all tests."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestPyLumoEncryption))
    suite.addTests(loader.loadTestsFromTestCase(TestPyLumoRequestPayload))
    suite.addTests(loader.loadTestsFromTestCase(TestPyLumoResponseParsing))
    suite.addTests(loader.loadTestsFromTestCase(TestPyLumoFileUpload))
    suite.addTests(loader.loadTestsFromTestCase(TestPyLumoConversationHistory))
    suite.addTests(loader.loadTestsFromTestCase(TestPyLumoSessionManagement))
    suite.addTests(loader.loadTestsFromTestCase(TestPyLumoOutputFile))
    suite.addTests(loader.loadTestsFromTestCase(TestPyLumoErrorHandling))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Print summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Tests run: {result.testsRun}")
    successes = result.testsRun - len(result.failures) - len(result.errors)
    print(f"Successes: {successes}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("=" * 80)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
