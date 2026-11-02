#!/usr/bin/env python3
"""
pylumo - A command line tool to interact with the Lumo Proton API.
"""
import argparse
import base64
import json
import logging
import os
import sys
import tempfile
import keyring
import uuid
import warnings
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, IO, List, Optional, Tuple, Union

# Suppress CryptographyDeprecationWarning from pgpy for 3DES
try:
    from cryptography.utils import CryptographyDeprecationWarning
    warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)
except ImportError:
    pass

import pgpy
import requests
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes

PROTON_API_URL = "https://account-api.proton.me"

# Import Proton API Session for authenticated mode
try:
    from proton.api import Session as ProtonSession
    from proton.constants import PUBKEY_HASH_DICT

    PROTON_API_AVAILABLE = True

    # Patch missing TLS pins for account.proton.me
    # The proton-python-client only has pins for VPN endpoints, not account.proton.me
    # This causes TLSPinningError when authenticating. We add the required pins here.
    # These pins should be updated if Proton rolls their certificates.
    # These hashes can be verified / updated with the following command:
    #  echo | openssl s_client -connect account.proton.me:443 -servername account.proton.me 2>/dev/null | openssl x509 -pubkey -noout | openssl pkey -pubin -outform DER | openssl dgst -sha256 -binary | base64
    if "account.proton.me" not in PUBKEY_HASH_DICT:
        PUBKEY_HASH_DICT["account.proton.me"] = [
            # Current certificate pin (as of Dec 2025)
            "CT56BhOTmj5ZIPgb/xD5mH8rY3BLo/MlhP7oPyJUEDo=",
            # Backup pins from Proton's alternative routing
            "EU6TS9MO0L/GsDHvVc9D5fChYLNy5JdGYpJw0ccgetM=",
            "iKPIHPnDNqdkvOnTClQ8zQAIKG0XavaPkcEo0LBAABA=",
            "MSlVrBCdL0hKyczvgYVSRNm88RicyY04Q2y5qrBt0xA=",
            "C2UxW0T1Ckl9s+8cXfjXxlEqwAfPM4HiW2y3UdtBeCw=",
        ]

    # account-api.proton.me is the JSON API host used by proton-python-client.
    # It typically uses the same certificate chain as account.proton.me.
    if "account-api.proton.me" not in PUBKEY_HASH_DICT:
        PUBKEY_HASH_DICT["account-api.proton.me"] = PUBKEY_HASH_DICT["account.proton.me"]
except ImportError:
    PROTON_API_AVAILABLE = False
    ProtonSession = None

# Make output look purrdy
try:
    from pygments import highlight
    from pygments.lexers import JsonLexer
    from pygments.formatters import TerminalFormatter
    PYGMENTS_AVAILABLE = True
except ImportError:
    PYGMENTS_AVAILABLE = False
    highlight = None
    JsonLexer = None
    TerminalFormatter = None

# Client Constants
LUMO_BASE_URL = "https://lumo.proton.me"
LUMO_API_URL = "https://lumo-api.proton.me/api/ai/v1/chat/completions"
# If Proton roll their key then we need to update this
LUMO_GPG_PUBLIC_KEY = """-----BEGIN PGP PUBLIC KEY BLOCK-----
xjMEaA9k7RYJKwYBBAHaRw8BAQdABaPA24xROahXs66iuekwPmdOpJbPE1a8A69r
siWP8rfNL1Byb3RvbiBMdW1vIChQcm9kIEtleSAwMDAyKSA8c3VwcG9ydEBwcm90
b24ubWU+wpkEExYKAEEWIQTwMqEWnd/47aco5ZqadMPvYVFKKgUCaA9k7QIbAwUJ
B4TOAAULCQgHAgIiAgYVCgkICwIEFgIDAQIeBwIXgAAKCRCadMPvYVFKKqiVAQD7
JNeudEXTaNMoQMkYjcutNwNAalwbLr5qe6N5rPogDQD/bA5KBWmDlvxVz7If6SBS
7Xzcvk8VMHYkBLKfh+bfUQzOOARoD2TtEgorBgEEAZdVAQUBAQdAnBIJoFt6Pxnp
RAJMHwhdCXaE+lwQFbKgwb6LCUFWvHYDAQgHwn4EGBYKACYWIQTwMqEWnd/47aco
5ZqadMPvYVFKKgUCaA9k7QIbDAUJB4TOAAAKCRCadMPvYVFKKkuRAQChUthLyAcc
UD6UrJkroc6exHIMSR5Vlk4d4L8OeFUWWAEA3ugyE/b/pSQ4WO+fiTkHN2ZeKlyj
dZMbxO6yWPA5uQk=
=h/mc
-----END PGP PUBLIC KEY BLOCK-----"""

# Limit the maximum size of file attachments to 2MB
MAX_FILE_SIZE = 2 * 1024 * 1024


# Available Lumo Tools - Will need to be updated as Proton update Lumo's toolset
class LumoTools(str, Enum):
    """Available tools that can be enabled in Lumo API requests.

    Tools extend Lumo's capabilities beyond basic text generation.
    Enable tools by passing their names to the `tools` parameter in send_request().

    Example:
        >>> client.send_request("Search for Python tutorials",
        ...                     tools=[LumoTools.WEB_SEARCH, LumoTools.PROTON_INFO])
    """

    # Internal tool - provides Proton-specific information and context
    PROTON_INFO = "proton_info"
    """Provides Proton-specific information and context.

    This is the default tool enabled for authenticated users.
    It allows Lumo to provide information about Proton services,
    account features, and product-specific guidance.
    """

    # External tools - require additional API calls
    WEB_SEARCH = "web_search"
    """Enables web search capability.

    Allows Lumo to search the web for current information.
    Useful for questions about recent events, current data,
    or topics that require up-to-date information.
    """

    WEATHER = "weather"
    """Provides weather information.

    Allows Lumo to fetch current weather data and forecasts
    for specified locations.
    """

    STOCK = "stock"
    """Provides stock market information.

    Allows Lumo to fetch current stock prices, market data,
    and financial information for publicly traded companies.
    """

    CRYPTOCURRENCY = "cryptocurrency"
    """Provides cryptocurrency information.

    Allows Lumo to fetch current cryptocurrency prices,
    market caps, and trading data.
    """


# Selectable Lumo AI models - Will need to be updated as Proton updates Lumo's model lineup
class LumoModel(str, Enum):
    """Selectable AI models for Lumo API requests.

    The value is the model ID sent in the request body's `model` field.
    Pick a model by passing a LumoModel (or its string) to the `model`
    parameter in send_request().

    Example:
        >>> client.send_request("Prove that sqrt(2) is irrational",
        ...                     model=LumoModel.LUMO_MAX)
    """

    AUTO = "auto"
    """Route to the best backend model for the task (default, recommended)."""

    LUMO_LITE = "lumo-lite"
    """Lumo Lite - fast, efficient model for everyday tasks."""

    LUMO_MAX = "lumo-max"
    """Lumo Max - more capable model for complex reasoning and longer context."""

    APERTUS_15 = "apertus-15"
    """Apertus 1.5 - fully open, Swiss-made model."""


# Message roles for conversation turns
class Role(str, Enum):
    """Roles for conversation turns in the Lumo API.

    These roles define the type of message in a conversation:
    - USER: Messages from the user
    - ASSISTANT: Responses from Lumo
    - SYSTEM: System-level instructions (rarely used directly)
    - TOOL_CALL: Internal tool invocation by the assistant
    - TOOL_RESULT: Result returned from a tool call
    """
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


# Response message types from the Lumo API
class ResponseMessageType(str, Enum):
    """Types of messages received in streaming responses from Lumo API.

    These indicate the current state or content type of the response stream.
    """
    QUEUED = "queued"
    """Request is queued and waiting to be processed."""

    INGESTING = "ingesting"
    """Server is processing/ingesting the request."""

    TOKEN_DATA = "token_data"
    """Streaming token data containing encrypted content."""

    DONE = "done"
    """Generation completed successfully."""

    TIMEOUT = "timeout"
    """Request timed out."""

    ERROR = "error"
    """An error occurred during generation."""

    REJECTED = "rejected"
    """Request was rejected (e.g., policy violation)."""

    HARMFUL = "harmful"
    """Content was flagged as potentially harmful."""


class LumoIntegrityError(RuntimeError):
    pass


# Context window limits (based on TypeScript implementation)
class ContextLimits:
    """Token limits for context window management.

    These limits help prevent context window overflow errors.
    Based on the official Lumo web client implementation.
    """
    WARNING_THRESHOLD = 90000   # Start warning at ~90K tokens
    DANGER_THRESHOLD = 100000   # Strong warning at ~100K tokens
    MAX_CONTEXT = 128000        # Maximum context window size


def estimate_token_count(text: str) -> int:
    """Estimate the number of tokens in a text string.

    Uses a simple approximation of ~4 characters per token,
    which is a reasonable estimate for English text with GPT-style tokenizers.

    Args:
        text: The text to estimate tokens for

    Returns:
        Estimated number of tokens

    Example:
        >>> estimate_token_count("Hello, world!")
        3
    """
    if not text:
        return 0
    # Approximate: 4 characters per token (standard GPT approximation)
    return len(text) // 4


def get_context_warning_level(token_count: int) -> str:
    """Get the warning level for a given token count.

    Args:
        token_count: Number of tokens in the context

    Returns:
        Warning level: 'none', 'warning', 'danger', or 'critical'
    """
    if token_count >= ContextLimits.MAX_CONTEXT:
        return "critical"
    elif token_count >= ContextLimits.DANGER_THRESHOLD:
        return "danger"
    elif token_count >= ContextLimits.WARNING_THRESHOLD:
        return "warning"
    return "none"


# Core pylumo client functionality
class pyLumo:
    """Base client for interacting with the Lumo Proton API using hybrid encryption.

    This client supports both authenticated (via Proton account) and guest modes.
    It handles AES-GCM encryption for messages and PGP encryption for key exchange.
    Conversation history is maintained and re-encrypted with each new request.
    """

    base_url: str
    quiet_mode: bool
    output_file: Optional[str]
    output_file_handle: Optional[IO[str]]
    pgp_key: Any  # pgpy.PGPKey type
    headers: Dict[str, str]
    conversation_history: List[Dict[str, Any]]  # Stores turn objects
    max_turns: int  # Maximum number of turns to keep in history
    # ProtonSession instance for authenticated mode
    proton_session: Optional[Any]
    authenticated_mode: bool  # Whether to use authenticated requests

    def _display_http_request(
        self, url: str, headers: Dict[str, str], payload: Dict[str, Any]
    ) -> None:
        """Display HTTP request details. No-op in base class, overridden in debug class."""
        pass

    def _display_http_response_start(self, response: requests.Response) -> None:
        """Display HTTP response headers. No-op in base class, overridden in debug class."""
        pass

    def _display_streaming_line(self, line: bytes) -> None:
        """Display individual streaming response line. No-op in base class. Override in subclasses."""
        pass

    def _display_http_response_end(
        self, content_by_target: Optional[Dict[str, str]] = None
    ) -> None:
        """Display end of HTTP response. No-op in base class, overridden in debug class."""
        pass

    def __init__(
        self,
        quiet_mode: bool = False,
        output_file: Optional[str] = None,
        guest_mode: bool = False,
        max_turns: int = 10,
    ) -> None:
        """Initialize the pyLumo client.

        Args:
            quiet_mode: If True, suppress output except for response content
            output_file: Optional file path to save output
            guest_mode: If True, use guest mode (currently unused)
            max_turns: Maximum conversation turns to keep in history (default: 10)
        """
        self.base_url = LUMO_API_URL
        self.quiet_mode = quiet_mode
        self.output_file = output_file
        self.output_file_handle = None
        self.conversation_history = []
        self.max_turns = max_turns
        self.proton_session = None
        self.authenticated_mode = False
        self._session_file_path: Optional[str] = None  # For auto-save after token refresh

        # Load PGP public key using PGPy (compatible with OpenPGP.js v6)
        lumo_public_key_text = self._load_lumo_public_key()
        pgp_key_tuple = pgpy.PGPKey.from_blob(lumo_public_key_text)
        self.pgp_key = (
            pgp_key_tuple[0] if isinstance(pgp_key_tuple, tuple) else pgp_key_tuple
        )

        self.headers = {
            "accept": "application/vnd.protonmail.v1+json",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "dnt": "1",
            "origin": LUMO_BASE_URL,
            "user-agent": "None",
            "x-pm-appversion": "Other",
            "x-pm-locale": "en_US",
        }

        if self.output_file:
            try:
                self.output_file_handle = open(self.output_file, "w", encoding="utf-8")
            except Exception as e:
                print(
                    f"Error opening output file '{self.output_file}': {e}",
                    file=sys.stderr,
                )
                self.output_file = None
                self.output_file_handle = None

    def _load_lumo_public_key(self) -> str:
        """Load the Lumo public PGP key.

        Returns:
            PGP public key as a string
        """
        return LUMO_GPG_PUBLIC_KEY

    @staticmethod
    def _get_secure_app_dir() -> Path:
        if sys.platform == "darwin":
            base_dir = Path.home() / "Library" / "Application Support"
        elif sys.platform == "win32":
            base_dir = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        else:
            base_dir = Path.home() / ".local" / "share"

        app_dir = base_dir / "pylumo"
        app_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.chmod(app_dir, 0o700)
        except Exception:
            pass
        return app_dir

    @staticmethod
    def _ensure_secure_dir(dir_path: Union[str, Path]) -> None:
        p = Path(dir_path)
        p.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.chmod(p, 0o700)
        except Exception:
            pass

    def authenticate_with_proton(
        self,
        username: str,
        password: str,
        log_dir: Optional[str] = None,
        cache_dir: Optional[str] = None,
        tls_pinning: bool = True,
    ) -> Dict[str, Any]:
        """Authenticate with Proton API and establish an authenticated session.

        Creates a Proton API session, authenticates with the provided credentials,
        and configures the client to use authenticated requests. Handles 2FA if enabled.
        Alternative routing is automatically enabled for better connectivity.

        Args:
            username: Proton account username (email address)
            password: Proton account password
            log_dir: Directory for Proton API logs (default: system temp dir)
            cache_dir: Directory for Proton API cache (default: system temp dir)
            tls_pinning: Enable TLS certificate pinning (default: True).
                Set to False if behind a corporate proxy or VPN that performs
                SSL inspection, which causes TLSPinningError. WARNING: Disabling
                TLS pinning reduces security - only use in trusted networks.

        Returns:
            Session information dict with keys: UID, AccessToken, RefreshToken,
            Scope, PasswordMode

        Raises:
            RuntimeError: If Proton API client is not available
            ValueError: If authentication or 2FA verification fails

        Example:
            >>> client = pyLumo()
            >>> session_info = client.authenticate_with_proton(
            ...     "user@proton.me",
            ...     "password123"
            ... )
            >>> # Now all requests will use authenticated session
            >>> response = client.send_request("Hello, Lumo!")

            # If behind a corporate proxy with SSL inspection:
            >>> session_info = client.authenticate_with_proton(
            ...     "user@proton.me",
            ...     "password123",
            ...     tls_pinning=False  # Disable pinning for proxy compatibility
            ... )
        """
        if not PROTON_API_AVAILABLE:
            raise RuntimeError(
                "Proton API client not available. "
                "If you installed via `make install-tui`, run using the project venv or uv: "
                "`uv run pylumo-tui` or `./.venv/bin/pylumo-tui` (or activate with `source .venv/bin/activate`)."
            )

        if log_dir is None or cache_dir is None:
            app_dir = self._get_secure_app_dir()
            if log_dir is None:
                log_dir = str(app_dir / "logs")
            if cache_dir is None:
                cache_dir = str(app_dir / "cache")

        self._ensure_secure_dir(log_dir)
        self._ensure_secure_dir(cache_dir)

        # Create Proton API session
        self.proton_session = ProtonSession(
            api_url=PROTON_API_URL,
            log_dir_path=log_dir,
            cache_dir_path=cache_dir,
            appversion="Other",
            user_agent="None",
            tls_pinning=tls_pinning,
        )

        # Suppress verbose proton-client logging (only show critical errors)
        logging.getLogger("proton-client").setLevel(logging.CRITICAL)

        # Enable alternative routing for better connectivity
        self.proton_session.enable_alternative_routing = True

        # Wrap api_request to capture auth response for 2FA detection
        original_api_request = self.proton_session.api_request
        last_auth_response = [None]

        def capture_auth_response(
            endpoint,
            jsondata=None,
            additional_headers=None,
            method=None,
            params=None,
            **kwargs,
        ):
            response = original_api_request(
                endpoint, jsondata, additional_headers, method, params, **kwargs
            )
            # Capture auth response for 2FA detection
            if endpoint == "/auth" and isinstance(response, dict):
                last_auth_response[0] = response
            return response

        self.proton_session.api_request = capture_auth_response

        # Authenticate. Proton's human-verification CAPTCHA cannot be solved by this
        # client: the old browser+paste-token path is dead (Proton never hands back a
        # copyable token). If a CAPTCHA is required, fail loudly and point the user to
        # the Arsylk/proton-auth adapter, login_via_proton_auth, which solves it.
        try:
            self.proton_session.authenticate(username, password)
        except Exception as e:
            # Proton returns API code 9001 when a human-verification CAPTCHA is required.
            if getattr(e, "code", None) == 9001 or "captcha" in str(e).lower():
                raise ValueError(
                    "Proton requires a human-verification CAPTCHA, which this client "
                    "cannot solve. Use login_via_proton_auth(client, username, password) "
                    "from pylumo.proton_auth, which delegates the CAPTCHA to the "
                    "Arsylk/proton-auth solver."
                ) from e
            raise ValueError(f"Authentication failed: {e}")

        # Check if 2FA is required by looking for 'twofactor' in scopes
        current_scope = self.proton_session.Scope
        if "twofactor" in current_scope and last_auth_response[0]:
            print("\nTwo-Factor Authentication Required")
            print("=" * 60)

            # Show 2FA methods available
            twofa_info = last_auth_response[0].get("2FA", {})
            if twofa_info.get("TOTP") == 1:
                print("  Available: TOTP (Authenticator App)")
            if twofa_info.get("FIDO2"):
                fido_keys = twofa_info["FIDO2"].get("RegisteredKeys", [])
                if fido_keys:
                    print(f"  Available: FIDO2/U2F ({len(fido_keys)} security key(s))")
                    for key in fido_keys:
                        print(f"    - {key.get('Name', 'Unknown key')}")

            print(f"\n  Current scope (limited): {', '.join(current_scope)}")
            print("  Full scope requires 2FA verification")

            # Prompt for 2FA code
            import getpass

            print()
            twofa_code = getpass.getpass("Enter 2FA code (TOTP): ")

            try:
                print("\nSubmitting 2FA code...")
                updated_scope = self.proton_session.provide_2fa(twofa_code)
                print(f"2FA successful! Updated scope: {updated_scope}")
                print("=" * 60)
            except Exception as e:
                raise ValueError(f"2FA verification failed: {e}")

        # Enable authenticated mode
        self.authenticated_mode = True

        # Return session information
        session_info = {
            "UID": self.proton_session.UID,
            "AccessToken": self.proton_session.AccessToken,
            "RefreshToken": self.proton_session.RefreshToken,
            "Scope": self.proton_session.Scope,
            "PasswordMode": self.proton_session.PasswordMode,
        }

        return session_info

    def logout(self) -> None:
        """Logout from Proton API and disable authenticated mode."""
        if self.proton_session:
            try:
                self.proton_session.logout()
            except Exception:
                # Catch network errors and other exceptions during logout
                # This is acceptable - we still clear the local session
                pass
            finally:
                self.proton_session = None
                self.authenticated_mode = False

    def save_session(self, filepath: str) -> None:
        """Save the current Proton session securely to the system keychain.

        Writes a reference file to 'filepath' containing the UID, while the
        sensitive session tokens are stored in the OS keychain.

        Args:
            filepath: Path to save the reference file

        Raises:
            RuntimeError: If no active session exists
            IOError: If file cannot be written
        """
        filepath = os.path.expanduser(filepath)
        if not self.proton_session:
            raise RuntimeError("No active Proton session to save")

        # 1. Get the full session dump
        session_dump = self.proton_session.dump()

        # 2. Extract the UID
        uid = self.proton_session.UID
        if not uid:
            raise ValueError("Cannot save session: UID not found")

        # 3. Store sensitive data in keychain (required for security)
        try:
            keyring.set_password("pylumo", uid, json.dumps(session_dump))
        except Exception as e:
            # Refuse to save if keyring fails - storing tokens in plain files is insecure
            raise RuntimeError(
                f"Cannot save session: Keyring storage failed ({e}). "
                "Session tokens cannot be stored securely without keychain access. "
                "Please ensure your system keychain is available and try again."
            )

        # 4. Write a pointer file to disk
        reference_data = {
            "storage_type": "keyring",
            "service": "pylumo",
            "uid": uid,
            "updated_at": datetime.now().isoformat(),
        }

        parent_dir = os.path.dirname(os.path.abspath(filepath)) or os.getcwd()
        try:
            os.makedirs(parent_dir, mode=0o700, exist_ok=True)
        except Exception:
            os.makedirs(parent_dir, exist_ok=True)

        fd: Optional[int] = None
        tmp_path: Optional[str] = None
        try:
            fd, tmp_path = tempfile.mkstemp(prefix=".pylumo-session-", dir=parent_dir, text=True)
            try:
                os.fchmod(fd, 0o600)
            except Exception:
                pass

            with os.fdopen(fd, "w", encoding="utf-8") as f:
                fd = None
                json.dump(reference_data, f, indent=2)

            os.replace(tmp_path, filepath)
            try:
                os.chmod(filepath, 0o600)
            except Exception:
                pass
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except Exception:
                    pass
            if tmp_path is not None and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    def load_session(
        self,
        filepath: str,
        log_dir: Optional[str] = None,
        cache_dir: Optional[str] = None,
        tls_pinning: bool = True,
    ) -> None:
        """Load a saved Proton session from file or keychain.

        Args:
            filepath: Path to the saved session file
            log_dir: Directory for Proton API logs
            cache_dir: Directory for Proton API cache
            tls_pinning: Enable TLS certificate pinning (default: True).
                Set to False if behind a corporate proxy or VPN that performs
                SSL inspection. WARNING: Disabling reduces security.

        Raises:
            RuntimeError: If Proton API client is not available
            FileNotFoundError: If session file doesn't exist
            ValueError: If session data is invalid or missing from keychain
        """
        filepath = os.path.expanduser(filepath)
        if not PROTON_API_AVAILABLE:
            raise RuntimeError(
                "Proton API client not available. "
                "If you installed via `make install-tui`, run using the project venv or uv: "
                "`uv run pylumo-tui` or `./.venv/bin/pylumo-tui` (or activate with `source .venv/bin/activate`)."
            )

        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Session file not found: {filepath}")

        if log_dir is None or cache_dir is None:
            app_dir = self._get_secure_app_dir()
            if log_dir is None:
                log_dir = str(app_dir / "logs")
            if cache_dir is None:
                cache_dir = str(app_dir / "cache")

        self._ensure_secure_dir(log_dir)
        self._ensure_secure_dir(cache_dir)

        # 1. Read the file from disk
        with open(filepath, "r") as f:
            try:
                file_data = json.load(f)
            except json.JSONDecodeError:
                raise ValueError("Corrupted session file")

        # 2. Determine if it's a pointer or legacy dump
        session_dump = None

        if isinstance(file_data, dict) and file_data.get("storage_type") == "keyring":
            # Pointer file
            uid = file_data.get("uid")
            if not uid:
                raise ValueError("Invalid session file: missing UID")

            # Retrieve from keychain
            try:
                stored_json = keyring.get_password("pylumo", uid)
                if not stored_json:
                    raise ValueError("Session expired or removed from keychain")
                session_dump = json.loads(stored_json)
            except Exception as e:
                raise RuntimeError(f"Failed to retrieve session from keychain: {e}")
        else:
            # Legacy mode
            session_dump = file_data

        # 2.5 Migrate older saved sessions that used the web host instead of the API host.
        if isinstance(session_dump, dict):
            api_url = session_dump.get("api_url")
            if api_url == "https://account.proton.me":
                session_dump["api_url"] = PROTON_API_URL

        # 3. Load the session
        self.proton_session = ProtonSession.load(
            dump=session_dump,
            log_dir_path=log_dir,
            cache_dir_path=cache_dir,
            tls_pinning=tls_pinning,
        )

        # Suppress verbose proton-client logging (only show critical errors)
        logging.getLogger("proton-client").setLevel(logging.CRITICAL)

        self.proton_session.enable_alternative_routing = True
        self.authenticated_mode = True

        # Store session file path for auto-save after token refresh
        self._session_file_path = filepath

    def delete_saved_session(self, filepath: str) -> None:
        """Delete a saved session from file and keychain.

        Args:
            filepath: Path to the saved session file
        """
        filepath = os.path.expanduser(filepath)
        if not os.path.exists(filepath):
            return

        try:
            with open(filepath, "r") as f:
                data = json.load(f)

            # Check if we used keyring
            if isinstance(data, dict) and data.get("storage_type") == "keyring":
                uid = data.get("uid")
                if uid:
                    try:
                        keyring.delete_password("pylumo", uid)
                    except Exception as e:
                        # Log warning but continue to delete file
                        print(
                            f"Warning: Failed to delete from keychain: {e}",
                            file=sys.stderr,
                        )

        except Exception:
            # If file is corrupt or not JSON, ignore and just delete file
            pass

        # Finally delete the file
        try:
            os.remove(filepath)
        except OSError as e:
            print(f"Error deleting session file: {e}", file=sys.stderr)

    def clear_conversation_history(self) -> None:
        """Clear the conversation history."""
        self.conversation_history = []

    def get_conversation_token_count(self) -> int:
        """Calculate the estimated token count for the current conversation history.

        Returns:
            Estimated total tokens in conversation history
        """
        total = 0
        for turn in self.conversation_history:
            content = turn.get("content", "")
            total += estimate_token_count(content)
            # Also count tool_call and tool_result content if present
            if "tool_call" in turn:
                total += estimate_token_count(turn["tool_call"])
            if "tool_result" in turn:
                total += estimate_token_count(turn["tool_result"])
        return total

    def get_context_status(self) -> Dict[str, Any]:
        """Get the current context window status.

        Returns:
            Dictionary with token count, warning level, and limits info

        Example:
            >>> status = client.get_context_status()
            >>> print(f"Tokens: {status['token_count']}, Level: {status['warning_level']}")
        """
        token_count = self.get_conversation_token_count()
        warning_level = get_context_warning_level(token_count)

        return {
            "token_count": token_count,
            "warning_level": warning_level,
            "max_context": ContextLimits.MAX_CONTEXT,
            "warning_threshold": ContextLimits.WARNING_THRESHOLD,
            "danger_threshold": ContextLimits.DANGER_THRESHOLD,
            "usage_percent": (token_count / ContextLimits.MAX_CONTEXT) * 100,
        }

    def add_turn_to_history(
        self,
        role: Union[str, Role],
        content: str,
        tool_call: Optional[str] = None,
        tool_result: Optional[str] = None,
    ) -> None:
        """Add a turn to the conversation history.

        This method properly handles all role types including tool_call and tool_result.

        Args:
            role: The role of the message (user, assistant, system, tool_call, tool_result)
            content: The message content
            tool_call: Optional tool call data (for assistant messages that invoke tools)
            tool_result: Optional tool result data (for tool response messages)
        """
        # Convert Role enum to string if needed
        role_str = role.value if isinstance(role, Role) else role

        turn = {
            "role": role_str,
            "content": content,
            "encrypted": False,
        }

        # Add tool-related fields if present
        if tool_call is not None:
            turn["tool_call"] = tool_call
        if tool_result is not None:
            turn["tool_result"] = tool_result

        self.conversation_history.append(turn)

        # Trim history to max_turns (keeping most recent)
        if len(self.conversation_history) > self.max_turns:
            self.conversation_history = self.conversation_history[-self.max_turns :]

    def _auto_trim_history(self, new_prompt: str) -> int:
        """Auto-trim conversation history to fit within context limits.

        Removes oldest conversation turns until the total token count
        (including the new prompt) fits within the context window.
        Leaves a safety margin of 10% to account for response tokens.

        Args:
            new_prompt: The new prompt about to be sent

        Returns:
            Number of turns removed from history
        """
        # Calculate tokens for new prompt
        new_prompt_tokens = estimate_token_count(new_prompt)

        # Leave 10% margin for response tokens and overhead
        safe_limit = int(ContextLimits.MAX_CONTEXT * 0.9)

        turns_removed = 0

        while self.conversation_history:
            # Calculate current total
            current_tokens = self.get_conversation_token_count() + new_prompt_tokens

            if current_tokens <= safe_limit:
                break

            # Remove oldest turn
            self.conversation_history.pop(0)
            turns_removed += 1

            if not self.quiet_mode and turns_removed == 1:
                print(
                    f"\n\033[33mAUTO-TRIM:\033[0m Context limit approaching "
                    f"({current_tokens:,} tokens). Trimming old messages...",
                    flush=True
                )

        if turns_removed > 0 and not self.quiet_mode:
            final_tokens = self.get_conversation_token_count() + new_prompt_tokens
            print(
                f"\033[33mAUTO-TRIM:\033[0m Removed {turns_removed} old turn(s). "
                f"New context size: {final_tokens:,} tokens\n",
                flush=True
            )

        return turns_removed

    def lumo_api_request(
        self,
        endpoint: str,
        jsondata: Optional[Dict[str, Any]] = None,
        additional_headers: Optional[Dict[str, str]] = None,
        method: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        stream: bool = False,
    ) -> requests.Response:
        """Make authenticated Lumo API request using Proton session.

        This method wraps the Proton session to make authenticated requests to
        the Lumo API. It handles session cookies and authorization headers automatically.

        Args:
            endpoint: Lumo API endpoint (e.g., "/api/ai/v1/chat/completions")
            jsondata: JSON data to send in the request body
            additional_headers: Additional headers to include
            method: HTTP method (get|post|put|delete|patch), auto-detected if None
            params: URL parameters to append
            stream: Whether to stream the response (default: False)

        Returns:
            Raw requests.Response object (not parsed JSON)

        Raises:
            RuntimeError: If no authenticated session is available
            ConnectionError: If connection fails
            TimeoutError: If request times out (30s timeout)
        """
        if not self.proton_session:
            raise RuntimeError(
                "No authenticated Proton session available. "
                "Call authenticate_with_proton() first."
            )

        # Determine HTTP method
        if method is None:
            method = "post" if jsondata is not None else "get"

        method = method.lower()
        method_map = {
            "get": self.proton_session.s.get,
            "post": self.proton_session.s.post,
            "put": self.proton_session.s.put,
            "delete": self.proton_session.s.delete,
            "patch": self.proton_session.s.patch,
        }

        fct = method_map.get(method)
        if fct is None:
            raise ValueError(f"Unknown method: {method}")

        # Build full URL (base_url is already the full chat completions URL)
        full_url = self.base_url

        # Prepare request kwargs
        request_kwargs = {
            "url": full_url,
            "timeout": 30,  # 30 second timeout
            "stream": stream,
        }

        if jsondata is not None:
            request_kwargs["json"] = jsondata

        if params is not None:
            request_kwargs["params"] = params

        if additional_headers is not None:
            request_kwargs["headers"] = additional_headers

        # Make the request with automatic token refresh on 401
        try:
            response = fct(**request_kwargs)

            # Check for 401 Unauthorized - token may have expired
            if response.status_code == 401:
                if not self.quiet_mode:
                    print(
                        "\n\033[33mTOKEN EXPIRED:\033[0m Access token invalid, "
                        "attempting refresh...",
                        file=sys.stderr,
                        flush=True
                    )

                # Try to refresh the tokens
                # NOTE: We bypass proton_session.refresh() and make a direct HTTP request because:
                # 1. The proton-python-client's api_request() method can return a raw Response
                #    object instead of parsed JSON when there's a JSON decode error with HTTP 200
                # 2. The api_request() method's URL routing can fail, returning HTML pages
                #    instead of API responses (observed: login page HTML with 200 status)
                # This workaround was implemented Dec 2025 after debugging token refresh failures.
                try:
                    refresh_url = f"{PROTON_API_URL}/auth/refresh"
                    refresh_payload = {
                        "ResponseType": "token",
                        "GrantType": "refresh_token",
                        "RefreshToken": self.proton_session.RefreshToken,
                        "RedirectURI": "http://protonmail.ch"
                    }

                    raw_response = self.proton_session.s.post(
                        refresh_url,
                        json=refresh_payload,
                        timeout=30
                    )

                    if raw_response.status_code == 401:
                        raise RuntimeError("Refresh token expired. Please login again.")

                    if raw_response.status_code != 200:
                        raise RuntimeError(f"Refresh failed with HTTP {raw_response.status_code}")

                    try:
                        refresh_response = raw_response.json()
                    except Exception as json_err:
                        text = raw_response.text[:200] if raw_response.text else "(empty)"
                        raise RuntimeError(f"Invalid JSON response: {json_err}. Body: {text}")

                    if not isinstance(refresh_response, dict):
                        raise RuntimeError(f"Unexpected response type: {type(refresh_response)}")

                    if "Code" in refresh_response and refresh_response["Code"] != 1000:
                        error_msg = refresh_response.get("Error", "Unknown error")
                        raise RuntimeError(f"Proton API error (Code {refresh_response['Code']}): {error_msg}")

                    if "AccessToken" not in refresh_response:
                        raise RuntimeError(f"Missing AccessToken in response. Keys: {list(refresh_response.keys())}")

                    # Update session with new tokens
                    self.proton_session._session_data["AccessToken"] = refresh_response["AccessToken"]
                    self.proton_session._session_data["RefreshToken"] = refresh_response["RefreshToken"]
                    self.proton_session.s.headers["Authorization"] = "Bearer " + self.proton_session.AccessToken

                    if not self.quiet_mode:
                        print(
                            "\033[32mTOKEN REFRESHED:\033[0m Successfully refreshed "
                            "tokens, retrying request...\n",
                            file=sys.stderr,
                            flush=True
                        )

                    # Retry the request with refreshed tokens
                    response = fct(**request_kwargs)

                    # If we have a session file path stored, update it
                    if hasattr(self, '_session_file_path') and self._session_file_path:
                        try:
                            self.save_session(self._session_file_path)
                            if not self.quiet_mode:
                                print(
                                    "\033[32mSESSION SAVED:\033[0m Updated session saved to disk\n",
                                    file=sys.stderr,
                                    flush=True
                                )
                        except Exception as save_error:
                            if not self.quiet_mode:
                                print(
                                    f"\033[33mWARNING:\033[0m Could not save refreshed session: {save_error}\n",
                                    file=sys.stderr,
                                    flush=True
                                )

                except Exception as refresh_error:
                    # Refresh failed - need to re-authenticate
                    if not self.quiet_mode:
                        print(
                            f"\033[31mTOKEN REFRESH FAILED:\033[0m {refresh_error}\n",
                            file=sys.stderr,
                            flush=True
                        )
                    raise RuntimeError(
                        f"Session expired. Please login again (^L). Details: {refresh_error}"
                    )

        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(f"Connection error: {e}")
        except requests.exceptions.Timeout as e:
            raise TimeoutError(f"Request timeout: {e}")
        except RuntimeError:
            raise  # Re-raise our RuntimeError from refresh failure
        except Exception as e:
            raise RuntimeError(f"Request failed: {e}")

        return response

    def create_request_payload(
        self,
        prompt: str,
        tools: Optional[List[str]] = None,
        targets: Optional[List[str]] = None,
        model: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], bytes]:
        """Create encrypted request payload for Lumo API.

        Args:
            prompt: User's message/prompt
            tools: List of tool names to enable
            targets: List of response targets (e.g., ['title', 'message'])
            model: Model ID to use (see LumoModel); None defaults to "auto"
            reasoning_effort: Reasoning mode to request; None defaults to
                "none" (Fast mode). Any other value selects Thinking mode.

        Returns:
            Tuple of (payload dict, AES key bytes)
        """
        if tools is None:
            tools = ["proton_info"]
        if targets is None:
            targets = ["title", "message"]
        if model is None:
            model = LumoModel.AUTO.value

        # Generate random values for each request
        aes_key = get_random_bytes(32)
        iv = get_random_bytes(12)
        request_id_uuid = uuid.uuid4()
        request_id = str(request_id_uuid)

        # Build turns list from conversation history
        turns = []

        # Use the same AEAD format as JavaScript: "lumo.request.{uuid}.turn"
        aead_data = f"lumo.request.{request_id}.turn".encode("utf-8")

        # Add conversation history (up to max_turns - 1 to leave room for current message)
        # Re-encrypt all messages with the new request key
        history_to_include = self.conversation_history[-(self.max_turns - 1) :]
        for turn in history_to_include:
            # Handle tool_call and tool_result as separate turns (matching TypeScript)
            # If a turn has tool_call/tool_result, we insert hidden turns before the main message
            if turn.get("tool_call") or turn.get("tool_result"):
                # Insert tool_call turn if present
                if turn.get("tool_call"):
                    tool_call_iv = get_random_bytes(12)
                    cipher_tool_call = AES.new(aes_key, AES.MODE_GCM, nonce=tool_call_iv)
                    cipher_tool_call.update(aead_data)
                    encrypted_tool_call, tool_call_tag = cipher_tool_call.encrypt_and_digest(
                        turn["tool_call"].encode("utf-8")
                    )
                    tool_call_turn = {
                        "role": Role.TOOL_CALL.value,
                        "content": base64.b64encode(
                            tool_call_iv + encrypted_tool_call + tool_call_tag
                        ).decode("utf-8"),
                        "encrypted": True,
                    }
                    turns.append(tool_call_turn)

                # Insert tool_result turn if present
                if turn.get("tool_result"):
                    tool_result_iv = get_random_bytes(12)
                    cipher_tool_result = AES.new(aes_key, AES.MODE_GCM, nonce=tool_result_iv)
                    cipher_tool_result.update(aead_data)
                    encrypted_tool_result, tool_result_tag = cipher_tool_result.encrypt_and_digest(
                        turn["tool_result"].encode("utf-8")
                    )
                    tool_result_turn = {
                        "role": Role.TOOL_RESULT.value,
                        "content": base64.b64encode(
                            tool_result_iv + encrypted_tool_result + tool_result_tag
                        ).decode("utf-8"),
                        "encrypted": True,
                    }
                    turns.append(tool_result_turn)

            # All messages in history are stored as cleartext
            # Encrypt them with the current request's AES key
            content = turn.get("content", "")
            if content:  # Only add if there's actual content
                turn_iv = get_random_bytes(12)
                cipher_turn = AES.new(aes_key, AES.MODE_GCM, nonce=turn_iv)
                cipher_turn.update(aead_data)
                encrypted_content, turn_tag = cipher_turn.encrypt_and_digest(
                    content.encode("utf-8")
                )
                encrypted_turn = {
                    "role": turn["role"],
                    "content": base64.b64encode(
                        turn_iv + encrypted_content + turn_tag
                    ).decode("utf-8"),
                    "encrypted": True,
                }
                turns.append(encrypted_turn)

        # AES-GCM does not require padding - encrypt the raw bytes
        cipher_aes = AES.new(aes_key, AES.MODE_GCM, nonce=iv)
        cipher_aes.update(aead_data)
        encrypted_prompt, tag = cipher_aes.encrypt_and_digest(prompt.encode("utf-8"))

        # Encrypt AES key with PGP using PGPy (compatible with OpenPGP.js v6)
        pgp_message = pgpy.PGPMessage.new(
            aes_key,
            format="b",
            compression=pgpy.constants.CompressionAlgorithm.Uncompressed,  # type: ignore
        )
        encrypted_pgp_message = self.pgp_key.encrypt(pgp_message)

        # Convert to binary and then base64 (matching OpenPGP.js binary format)
        pgp_binary = bytes(encrypted_pgp_message)
        b64_body = base64.b64encode(pgp_binary).decode("utf-8")

        # Add current user message
        current_user_turn = {
            "role": "user",
            "content": base64.b64encode(iv + encrypted_prompt + tag).decode("utf-8"),
            "encrypted": True,
        }
        turns.append(current_user_turn)

        # Build the OpenAI-compatible chat completions body (ChatCompletionsRequest).
        # The legacy {"Prompt": ...} schema is deprecated and the API rejects it with
        # HTTP 400; the live endpoint expects model + messages + stream + a `lumo`
        # extension carrying the U2L encryption params (request_key/request_id).
        lumo_ext = {
            "client_type": "frontend",
            "target": "message",
            "request_key": b64_body,
            "request_id": request_id,
        }
        payload = {
            "model": model,
            "messages": turns,
            "stream": True,
            "stream_options": {"include_usage": True},
            "reasoning_effort": reasoning_effort or "none",
            "lumo": lumo_ext,
        }
        if tools:
            # OpenAI shape: each built-in tool is a {"name": ...} object, not a bare
            # string (the live API rejects a string array with HTTP 422).
            payload["tools"] = [{"name": tool} for tool in tools]
            payload["tool_choice"] = "auto"
        return payload, aes_key

    def send_request(
        self,
        prompt: str,
        tools: Optional[List[str]] = None,
        targets: Optional[List[str]] = None,
        stream_callback: Optional[Callable[[str, str], None]] = None,
        model: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
    ) -> Dict[str, str]:
        """Send an encrypted request to the Lumo API.

        This method creates an encrypted payload, sends it to the API, and handles
        the streaming response. Conversation history is automatically maintained.

        Args:
            prompt: User's message/prompt to send
            tools: List of tool names to enable (default: ["proton_info"])
            targets: Response targets to request (default: ["title", "message"])
            stream_callback: Optional callback function(target, chunk) for streaming
            model: Model ID to use (see LumoModel); None defaults to "auto"
            reasoning_effort: Reasoning mode to request; None defaults to
                "none" (Fast mode), any other value selects Thinking mode

        Returns:
            Dictionary mapping target names to their response content,
            carrying a "reasoning" key when Thinking mode produced any

        Example:
            >>> client = pyLumo()
            >>> response = client.send_request("What is Proton?")
            >>> print(response["message"])
        """
        # Auto-trim conversation history if approaching context limit
        self._auto_trim_history(prompt)

        payload, aes_key = self.create_request_payload(
            prompt, tools, targets, model, reasoning_effort
        )

        try:
            request_start_time = datetime.now()
            self._display_http_request(self.base_url, self.headers, payload)

            # Use authenticated session if available, otherwise standard requests
            if self.authenticated_mode and self.proton_session:
                # Use the lumo_api_request method (wraps Proton session)
                response = self.lumo_api_request(
                    endpoint="/api/ai/v1/chat/completions",
                    jsondata=payload,
                    method="post",
                    stream=True,
                )
            else:
                # Standard unauthenticated request
                response = requests.post(
                    self.base_url,
                    headers=self.headers,
                    json=payload,
                    stream=True,
                    timeout=30,
                )

            request_id_str = payload["lumo"]["request_id"]
            content_by_target, timestamps_by_target = self.parse_streaming_response(
                response, request_start_time, aes_key, request_id_str, stream_callback
            )

            if not self.quiet_mode:
                self._print_final_summary(
                    request_start_time, content_by_target, timestamps_by_target
                )

            # Store the user message and assistant response in conversation history
            # Store as CLEARTEXT so they can be re-encrypted with new keys in
            # future requests
            self.add_turn_to_history(Role.USER, prompt)

            # Store assistant response with tool_call and tool_result if present
            if "message" in content_by_target and content_by_target["message"]:
                tool_call_content = content_by_target.get("tool_call")
                tool_result_content = content_by_target.get("tool_result")

                self.add_turn_to_history(
                    Role.ASSISTANT,
                    content_by_target["message"],
                    tool_call=tool_call_content,
                    tool_result=tool_result_content,
                )

            return content_by_target
        except Exception as e:
            print(f"\n\033[1;31mERROR:\033[0m Request failed: {e}")
            return {}

    def _print_final_summary(
        self,
        request_start_time: datetime,
        content_by_target: Dict[str, str],
        timestamps_by_target: Dict[str, List[datetime]],
    ) -> None:
        """Print final statistics and response summary. No-op in base class."""
        pass

    def parse_streaming_response(
        self,
        response: requests.Response,
        request_start_time: datetime,
        aes_key: bytes,
        request_id: str,
        stream_callback: Optional[Callable[[str, str], None]] = None,
        raise_on_integrity_error: bool = False,
    ) -> Tuple[Dict[str, str], Dict[str, List[datetime]]]:
        """Parse and decrypt streaming SSE response from Lumo API.

        Processes the live OpenAI-shaped Server-Sent Events (SSE) stream from
        /api/ai/v1/chat/completions, branching on each chunk's `object`
        discriminator (chat.completion.chunk / chat.tool_call / chat.tool_result),
        decrypts each encrypted field with AES-GCM, and accumulates content by target.

        Args:
            response: Streaming HTTP response object
            request_start_time: Timestamp when request was initiated
            aes_key: AES key used for decryption (32 bytes)
            request_id: UUID of the request for AEAD data
            stream_callback: Optional callback function(target, chunk) for real-time updates

        Returns:
            Tuple of (content_by_target dict, timestamps_by_target dict)
        """
        content_by_target = {}
        timestamps_by_target = {}

        integrity_error: Optional[Exception] = None

        # Response AEAD associated data (matches TypeScript: "lumo.response.{uuid}.chunk")
        aead_data = f"lumo.response.{request_id}.chunk".encode("utf-8")

        def decrypt_chunk(encrypted_b64: str) -> str:
            # base64 -> iv(12) + ciphertext + tag(16), decrypt_and_verify with AES-GCM
            decoded = base64.b64decode(encrypted_b64)
            if len(decoded) < (12 + 16):
                raise ValueError(
                    f"Encrypted chunk too short: {len(decoded)} bytes"
                )
            iv = decoded[:12]
            ciphertext = decoded[12:-16]
            tag = decoded[-16:]
            cipher = AES.new(aes_key, AES.MODE_GCM, nonce=iv)
            cipher.update(aead_data)
            return cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8")

        def accumulate(target: str, text: str, response_time: datetime) -> None:
            if target not in content_by_target:
                content_by_target[target] = ""
                timestamps_by_target[target] = []
            content_by_target[target] += text
            timestamps_by_target[target].append(response_time)
            # Call the stream callback for real-time updates (if provided)
            if stream_callback and text:
                stream_callback(target, text)

        # Tool-call accumulator keyed by call id (matches TypeScript StreamProcessor Map)
        tool_calls: Dict[str, Dict[str, str]] = {}

        def render_tool_calls() -> str:
            calls = [
                {"id": c["id"], "name": c["name"], "arguments": c["arguments"]}
                for c in tool_calls.values()
                if c["name"]
            ]
            if not calls:
                return ""
            return json.dumps(calls[0]) if len(calls) == 1 else json.dumps(calls)

        try:
            response.raise_for_status()
            self._display_http_response_start(response)

            for line in response.iter_lines():
                if integrity_error is not None:
                    break
                self._display_streaming_line(line)
                if not line or not line.strip():
                    continue
                if isinstance(line, bytes):
                    line = line.decode("utf-8")
                trimmed = line.strip()

                # SSE comment lines carry lifecycle events (": queued", ": ingesting")
                if trimmed.startswith(":"):
                    comment = trimmed[1:].strip()
                    if not self.quiet_mode:
                        if comment == "queued":
                            print("\\r⏳ Request queued...", end="", flush=True)
                        elif comment == "ingesting":
                            print("\\r🔄 Processing...", end="", flush=True)
                    continue

                # Extract JSON payload: "data: {...}" prefix or bare "{...}" line
                if trimmed.startswith("data:"):
                    json_data = trimmed[5:].strip()
                elif trimmed.startswith("{"):
                    json_data = trimmed
                else:
                    continue

                if not json_data:
                    continue

                # [DONE] sentinel marks the end of the stream
                if json_data == "[DONE]":
                    if not self.quiet_mode:
                        print()  # New line after streaming
                    continue

                try:
                    data = json.loads(json_data)
                    response_time = datetime.now()

                    # Branch on the chunk's `object` discriminator (OpenAI shape)
                    obj = data.get("object", "")

                    if obj == "chat.tool_call":
                        # Tool call declaration: {id, name, arguments?, encrypted}
                        tc = data.get("tool_call", {})
                        call_id = tc.get("id", "")
                        if call_id not in tool_calls:
                            tool_calls[call_id] = {
                                "id": call_id,
                                "name": "",
                                "arguments": "",
                            }
                        acc = tool_calls[call_id]
                        if tc.get("name"):
                            acc["name"] = tc["name"]
                        if tc.get("arguments"):
                            args = tc["arguments"]
                            if tc.get("encrypted"):
                                args = decrypt_chunk(args)
                            acc["arguments"] += args
                        content_by_target["tool_call"] = render_tool_calls()

                    elif obj == "chat.tool_result":
                        # Tool result: {call_id, content, encrypted}
                        tr = data.get("tool_result", {})
                        content = tr.get("content", "")
                        if content:
                            if tr.get("encrypted"):
                                content = decrypt_chunk(content)
                            accumulate("tool_result", content, response_time)

                    else:
                        # chat.completion.chunk (or bare choices chunk)
                        if data.get("error"):
                            error = data["error"]
                            error_msg = error.get("message", "Unknown error")
                            content_by_target["_error"] = error_msg
                            if not self.quiet_mode:
                                print(
                                    f"\n\033[31mERROR:\033[0m Stream error: {error_msg}",
                                    file=sys.stderr,
                                    flush=True,
                                )
                            continue

                        if data.get("usage"):
                            content_by_target["usage"] = json.dumps(data["usage"])

                        choices = data.get("choices")
                        if not choices:
                            continue

                        choice = choices[0]
                        finish_reason = choice.get("finish_reason")
                        if finish_reason == "content_filter":
                            if not self.quiet_mode:
                                print(
                                    "\n\033[31mHARMFUL:\033[0m Content flagged as potentially harmful"
                                )
                            content_by_target["_error"] = "harmful_content"
                            continue

                        delta = choice.get("delta")
                        if not delta:
                            continue

                        # Target: delta.target ?? chunk.target ?? "message"
                        target = delta.get("target") or data.get("target") or "message"

                        content = delta.get("content")
                        if isinstance(content, str) and content:
                            if delta.get("encrypted"):
                                content = decrypt_chunk(content)
                            accumulate(target, content, response_time)
                            if target == "message" and not self.quiet_mode:
                                print(content, end="", flush=True)

                        reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                        if isinstance(reasoning, str) and reasoning:
                            if delta.get("encrypted"):
                                reasoning = decrypt_chunk(reasoning)
                            accumulate("reasoning", reasoning, response_time)

                        tool_call_deltas = delta.get("tool_calls")
                        if isinstance(tool_call_deltas, list):
                            for tcd in tool_call_deltas:
                                fn = tcd.get("function", {})
                                idx = tcd.get("index", 0)
                                key = tcd.get("id") or f"call_{idx}"
                                if key not in tool_calls:
                                    tool_calls[key] = {
                                        "id": key,
                                        "name": "",
                                        "arguments": "",
                                    }
                                acc = tool_calls[key]
                                if fn.get("name"):
                                    acc["name"] = fn["name"]
                                if fn.get("arguments"):
                                    args = fn["arguments"]
                                    if delta.get("encrypted"):
                                        args = decrypt_chunk(args)
                                    acc["arguments"] += args
                            content_by_target["tool_call"] = render_tool_calls()
                except json.JSONDecodeError:
                    if not self.quiet_mode:
                        print(
                            f"\n\033[33mWARNING:\033[0m Could not parse JSON data: {json_data[:50]}..."
                        )
                    continue
                except Exception as e:
                    integrity_error = e
                    content_by_target["_error"] = "integrity_error"
                    content_by_target["_error_details"] = str(e)
                    if not self.quiet_mode:
                        print(
                            "\n\033[31mINTEGRITY ERROR:\033[0m "
                            f"Response decryption failed: {e}",
                            file=sys.stderr,
                            flush=True,
                        )
                    try:
                        response.close()
                    except Exception:
                        pass
                    if raise_on_integrity_error:
                        raise LumoIntegrityError(
                            f"Response integrity verification failed: {e}"
                        )
                    break

        except LumoIntegrityError:
            # Integrity error occurred ensure it raised and accessible for lib users not swallowed
            raise
        except Exception as e:
            print(f"\n\033[33mWARNING:\033[0m An error occurred: {e}")

        self._display_http_response_end(content_by_target)
        return content_by_target, timestamps_by_target

    def format_file_upload(self, file_path: str) -> str:
        """Read a file and format it for upload.

        Binary files are base64-encoded, text files are included as-is.

        Args:
            file_path: Path to the file to upload

        Returns:
            Formatted string with filename and file content

        Raises:
            FileNotFoundError: If the file doesn't exist
            IOError: If there's an error reading the file
        """
        # Get the filename from the path
        filename = os.path.basename(file_path)

        # Read the file in binary mode
        try:
            # Check file size first (deault limit: 2MB)
            file_size = os.path.getsize(file_path)
            if file_size > MAX_FILE_SIZE:
                raise ValueError(
                    f"File size ({file_size / (1024*1024):.2f} MB) exceeds {MAX_FILE_SIZE / (1024*1024):.2f}MB limit"
                )

            with open(file_path, "rb") as f:
                file_content = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {file_path}")
        except Exception as e:
            raise IOError(f"Error reading file {file_path}: {e}")

        # Check if file is binary by trying to decode as UTF-8
        try:
            text_content = file_content.decode("utf-8")
            # If file contains null bytes, treat as binary
            is_binary = "\x00" in text_content
        except (UnicodeDecodeError, AttributeError):
            is_binary = True

        # Format the upload string
        if is_binary:
            # Base64 encode binary content
            encoded_content = base64.b64encode(file_content).decode("utf-8")
            formatted_upload = (
                f"Filename: {filename}\n"
                f"File contents (base64-encoded):\n"
                f"----- BEGIN FILE CONTENTS -----\n"
                f"{encoded_content}\n"
                f"----- END FILE CONTENTS -----"
            )
        else:
            # Include text content as-is
            formatted_upload = (
                f"Filename: {filename}\n"
                f"File contents:\n"
                f"----- BEGIN FILE CONTENTS -----\n"
                f"{text_content}\n"
                f"----- END FILE CONTENTS -----"
            )

        return formatted_upload

    def send_request_with_file(
        self,
        prompt: str,
        file_path: str,
        tools: Optional[List[str]] = None,
        targets: Optional[List[str]] = None,
        model: Optional[str] = None,
    ) -> Dict[str, str]:
        """Send a request with an attached file.

        Args:
            prompt: The user's message/prompt
            file_path: Path to the file to upload
            tools: Optional list of tool names
            targets: Optional list of response targets
            model: Model ID to use (see LumoModel); None defaults to "auto"

        Returns:
            Dictionary with response content by target
        """
        # Format the file upload
        file_upload_str = self.format_file_upload(file_path)

        # Append the file upload to the prompt
        combined_prompt = f"{prompt}\n\n{file_upload_str}"

        # Send the request with the combined prompt
        return self.send_request(combined_prompt, tools, targets, model=model)


# Very Basic CLI
def main() -> None:
    """Main entry point for the pyLumo command-line interface.

    Parses command-line arguments and sends requests to the Lumo API.
    Supports both standard and debug modes, file uploads, and stdin input.
    """
    # Import pyLumoDebug for debug mode
    from pylumo import _pylumo_debug
    pyLumoDebug = _pylumo_debug.pyLumoDebug

    parser = argparse.ArgumentParser(
        description="pyLumo - Send requests to Lumo Proton API with hybrid encryption",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        help="The prompt to send to the API (optional if using stdin)",
    )
    parser.add_argument(
        "--tools",
        nargs="+",
        default=[],
        help="Tools to include in the request (empty for guest mode)",
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        default=["title", "message"],
        help="Targets for the response",
    )
    parser.add_argument(
        "--model",
        default="auto",
        choices=["auto", "lumo-lite", "lumo-max", "apertus-15"],
        help="Model to use (default: auto)",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Quiet mode (raw output only)"
    )
    parser.add_argument(
        "-d", "--debug", action="store_true", help="Debug mode (HTTP debugging)"
    )
    parser.add_argument("-o", "--output", help="Save output to file")
    parser.add_argument(
        "-u",
        "--upload",
        metavar="FILE",
        help="Upload a file (base64-encoded if binary)",
    )

    args = parser.parse_args()

    if args.prompt:
        prompt = args.prompt
    elif not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
    else:
        print("Error: No prompt provided.", file=sys.stderr)
        parser.print_help()
        sys.exit(1)

    # Use pyLumoDebug if debug mode is enabled, otherwise use base pyLumo
    if args.debug:
        client = pyLumoDebug(
            quiet_mode=args.quiet,
            output_file=args.output,
        )
    else:
        client = pyLumo(
            quiet_mode=args.quiet,
            output_file=args.output,
        )

    # Send request with file upload if -u option is provided
    if args.upload:
        client.send_request_with_file(
            prompt=prompt,
            file_path=args.upload,
            tools=args.tools,
            targets=args.targets,
            model=args.model,
        )
    else:
        client.send_request(
            prompt=prompt,
            tools=args.tools,
            targets=args.targets,
            model=args.model,
        )


if __name__ == "__main__":
    main()
