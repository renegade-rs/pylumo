#!/usr/bin/env python3
"""
pyLumoDebug - Debug client with verbose logging for development and debugging.
"""
import os
import json
import sys
import logging
import getpass
import keyring
from datetime import datetime
from typing import Callable, Dict, Any, List, Optional

# Import base pyLumo class
from pylumo import pylumo as pylumo_module
pyLumo = pylumo_module.pyLumo
PROTON_API_AVAILABLE = pylumo_module.PROTON_API_AVAILABLE

# Conditional import for Proton API
if PROTON_API_AVAILABLE:
    from proton.api import Session as ProtonSession
else:
    ProtonSession = None


class pyLumoDebug(pyLumo):
    """Debug client with verbose HTTP/response logging for development and debugging.
    All HTTP requests and responses are logged to stderr in raw mode."""

    # Debug output formatting constant
    DEBUG_LINE_WIDTH = 78

    raw_mode: bool

    def __init__(
        self,
        quiet_mode: bool = False,
        output_file: Optional[str] = None,
        guest_mode: bool = False,
        skip_2fa_prompt: bool = False,
    ) -> None:
        super().__init__(quiet_mode, output_file, guest_mode)
        self.raw_mode = True
        self.skip_2fa_prompt = skip_2fa_prompt  # Allow TUI to handle 2FA

    # Override core methods to add debug output
    def authenticate_with_proton(
        self,
        username: str,
        password: str,
        log_dir: Optional[str] = None,
        cache_dir: Optional[str] = None,
        tls_pinning: bool = True,
    ) -> Dict[str, Any]:
        """Authenticate with Proton API with debug output.

        Args:
            username: Proton account username
            password: Proton account password
            log_dir: Directory for Proton API logs
            cache_dir: Directory for Proton API cache
            tls_pinning: Enable TLS certificate pinning (default: True).
                Set to False if behind a corporate proxy/VPN with SSL inspection.
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

        # Get API URL from parent class logic
        api_url = pylumo_module.PROTON_API_URL

        # Create Proton API session
        self.proton_session = ProtonSession(
            api_url=api_url,
            log_dir_path=log_dir,
            cache_dir_path=cache_dir,
            appversion="Other",
            user_agent="None",
            tls_pinning=tls_pinning,
            timeout=30,  # Workaround for bug in proton-python-client
        )

        # Enable alternative routing for better connectivity
        self.proton_session.enable_alternative_routing = True

        # --- Advanced Debug Logger ---
        self.request_counter = 0

        def _mask_sensitive_data(data):
            """Mask sensitive fields in request/response data."""
            sensitive_fields = [
                "ClientEphemeral",
                "ClientProof",
                "ServerProof",
                "AccessToken",
                "RefreshToken",
                "Password",
                "TwoFactorCode",
            ]
            if isinstance(data, dict):
                for key, value in data.items():
                    if key in sensitive_fields:
                        if key == "TwoFactorCode":
                            data[key] = "****** [MASKED]"
                        else:
                            data[key] = f"{str(value)[:10]}... [MASKED]"
                    elif isinstance(value, (dict, list)):
                        _mask_sensitive_data(value)
            elif isinstance(data, list):
                for item in data:
                    _mask_sensitive_data(item)
            return data

        original_send = self.proton_session.s.send

        def patched_send(request, **kwargs):
            """Patched send method to log HTTP requests and responses."""
            self.request_counter += 1
            # Print Request
            print("\n" + "─" * self.DEBUG_LINE_WIDTH, file=sys.stderr)
            print(
                f"\033[1;36mREQUEST #{
                    self.request_counter}\033[0m",
                file=sys.stderr,
            )
            print("─" * self.DEBUG_LINE_WIDTH, file=sys.stderr)
            print(f"Method: {request.method}", file=sys.stderr)
            print(f"Full URL: {request.url}", file=sys.stderr)
            print("\nSession Headers:", file=sys.stderr)
            for header, value in request.headers.items():
                if header.lower() in ["authorization", "x-pm-uid", "cookie"]:
                    print(f"  {header}: {value[:30]}... [MASKED]", file=sys.stderr)
                else:
                    print(f"  {header}: {value}", file=sys.stderr)
            if request.body:
                print("\nRequest Body:", file=sys.stderr)
                try:
                    body_json = json.loads(request.body)
                    masked_body = _mask_sensitive_data(body_json)
                    print(json.dumps(masked_body, indent=2), file=sys.stderr)
                except (json.JSONDecodeError, TypeError):
                    print(request.body, file=sys.stderr)

            # Get Response
            response = original_send(request, **kwargs)

            # Print Response
            print("\n" + "─" * self.DEBUG_LINE_WIDTH, file=sys.stderr)
            print(
                f"\033[1;32mRESPONSE #{
                    self.request_counter}\033[0m",
                file=sys.stderr,
            )
            print("─" * self.DEBUG_LINE_WIDTH, file=sys.stderr)
            print(
                f"Status: \033[1;32m{
                    response.status_code} {
                    response.reason}\033[0m",
                file=sys.stderr,
            )
            print("\nResponse Headers:", file=sys.stderr)
            for header, value in response.headers.items():
                if header.lower() in ["set-cookie"]:
                    print(f"  {header}: {value[:50]}... [TRUNCATED]", file=sys.stderr)
                else:
                    print(f"  {header}: {value}", file=sys.stderr)
            if response.text:
                print("\nResponse Body:", file=sys.stderr)
                try:
                    body_json = response.json()
                    # No masking for response body to see all details
                    print(json.dumps(body_json, indent=2), file=sys.stderr)
                except (json.JSONDecodeError, TypeError):
                    print(response.text, file=sys.stderr)
            print("=" * self.DEBUG_LINE_WIDTH + "\n", file=sys.stderr)

            return response

        self.proton_session.s.send = patched_send

        print("\n" + "=" * self.DEBUG_LINE_WIDTH, file=sys.stderr)
        print("\033[1;33mPROTON AUTHENTICATION\033[0m", file=sys.stderr)
        print("=" * self.DEBUG_LINE_WIDTH, file=sys.stderr)
        print(f"Username: {username}", file=sys.stderr)
        print(f"Password: {'*' * 12} [MASKED]", file=sys.stderr)
        print(f"Log directory: {log_dir}", file=sys.stderr)
        print(f"Cache directory: {cache_dir}", file=sys.stderr)
        print("\nCreating Proton API session...", file=sys.stderr)
        print(f"   API URL: {api_url}", file=sys.stderr)
        tls_status = "Enabled" if tls_pinning else "DISABLED (insecure)"
        print(f"   TLS pinning: {tls_status}", file=sys.stderr)
        print(
            "   Alternative routing: Disabled (direct connection only)", file=sys.stderr
        )
        print("\nAuthenticating with Proton...", file=sys.stderr)

        # Authenticate and check the returned scope for 2FA requirement
        try:
            auth_response = self.proton_session.authenticate(username, password)
        except Exception as e:
            print(f"Authentication failed: {e}", file=sys.stderr)
            raise

        # The 2FA flow: check if 'twofactor' is in the returned scope list
        if isinstance(auth_response, list) and "twofactor" in auth_response:
            print("\n" + "=" * self.DEBUG_LINE_WIDTH, file=sys.stderr)
            print(
                "\033[1;33mTWO-FACTOR AUTHENTICATION REQUIRED\033[0m", file=sys.stderr
            )
            print("=" * self.DEBUG_LINE_WIDTH, file=sys.stderr)
            print(
                f"  Current scope (limited): {
                    self.proton_session.Scope}",
                file=sys.stderr,
            )
            print("  Full scope requires 2FA verification", file=sys.stderr)
            if self.skip_2fa_prompt:
                print("  WARNING: 2FA prompt skipped (TUI mode)", file=sys.stderr)
            print("=" * self.DEBUG_LINE_WIDTH + "\n", file=sys.stderr)

            # If skip_2fa_prompt is set (e.g., in TUI mode), return early
            if self.skip_2fa_prompt:
                self.authenticated_mode = True  # Partially authenticated
                return {
                    "UID": self.proton_session.UID,
                    "AccessToken": self.proton_session.AccessToken,
                    "RefreshToken": self.proton_session.RefreshToken,
                    "Scope": self.proton_session.Scope,
                    "PasswordMode": self.proton_session.PasswordMode,
                    "TwoFactorRequired": True,
                }

            # Prompt for 2FA code (CLI mode)
            twofa_code = getpass.getpass("Enter 2FA code (TOTP): ")

            try:
                self.proton_session.provide_2fa(twofa_code)
            except Exception as e:
                raise ValueError(f"2FA verification failed: {e}")

        # Enable authenticated mode
        self.authenticated_mode = True

        print("\n" + "=" * self.DEBUG_LINE_WIDTH, file=sys.stderr)
        print("\033[1;32mAUTHENTICATION SUCCESSFUL\033[0m", file=sys.stderr)
        print("=" * self.DEBUG_LINE_WIDTH, file=sys.stderr)
        print(f"   UID: {self.proton_session.UID}", file=sys.stderr)
        if hasattr(self.proton_session, "AccessToken"):
            token_len = len(self.proton_session.AccessToken) if self.proton_session.AccessToken else 0
            print(
                f"   AccessToken: {'*' * 32} [REDACTED, {token_len} chars]",
                file=sys.stderr,
            )
        if hasattr(self.proton_session, "Scope"):
            print(f"   Scope: {self.proton_session.Scope}", file=sys.stderr)
        print("=" * self.DEBUG_LINE_WIDTH + "\n", file=sys.stderr)

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
        """Logout with debug output."""
        print("\n" + "=" * self.DEBUG_LINE_WIDTH, file=sys.stderr)
        print("\033[1;33mLOGOUT\033[0m", file=sys.stderr)
        print("=" * self.DEBUG_LINE_WIDTH, file=sys.stderr)
        print("Logging out from Proton API...", file=sys.stderr)

        if self.proton_session:
            # Temporarily suppress proton-client logging to avoid verbose
            # tracebacks
            proton_logger = logging.getLogger("proton-client")
            original_level = proton_logger.level
            proton_logger.setLevel(logging.CRITICAL)

            try:
                super().logout()
                print("\033[1;32mLogged out successfully\033[0m", file=sys.stderr)
            except Exception as e:
                error_msg = str(e)
                network_errors = [
                    "NameResolutionError",
                    "Max retries exceeded",
                    "Connection refused",
                ]
                if any(err in error_msg for err in network_errors):
                    print(
                        "\033[1;33mWARNING:\033[0m Network error during logout (offline or connection refused)",
                        file=sys.stderr,
                    )
                    print("   Local session will still be cleared", file=sys.stderr)
                else:
                    print(
                        f"\033[1;33mWARNING:\033[0m Logout API call failed: {error_msg[:100]}",
                        file=sys.stderr,
                    )
                    print("   Local session will still be cleared", file=sys.stderr)
            finally:
                # Restore proton-client logging level
                proton_logger.setLevel(original_level)
                print("   Session cleared locally", file=sys.stderr)
                print("   Authenticated mode: Disabled", file=sys.stderr)
                print("=" * self.DEBUG_LINE_WIDTH + "\n", file=sys.stderr)
        else:
            print("WARNING: No active session to logout", file=sys.stderr)
            print("=" * self.DEBUG_LINE_WIDTH + "\n", file=sys.stderr)

    def save_session(self, filepath: str) -> None:
        """Save session with debug output."""
        if not self.proton_session:
            print("\n" + "=" * self.DEBUG_LINE_WIDTH, file=sys.stderr)
            print("\033[1;33mSAVE SESSION\033[0m", file=sys.stderr)
            print("=" * self.DEBUG_LINE_WIDTH, file=sys.stderr)
            print(
                "\033[1;31mERROR:\033[0m No active Proton session to save",
                file=sys.stderr,
            )
            print("=" * self.DEBUG_LINE_WIDTH + "\n", file=sys.stderr)
            raise RuntimeError("No active Proton session to save")

        print("\n" + "=" * self.DEBUG_LINE_WIDTH, file=sys.stderr)
        print("\033[1;33mSAVE SESSION\033[0m", file=sys.stderr)
        print("=" * self.DEBUG_LINE_WIDTH, file=sys.stderr)
        print(f"File path: {filepath}", file=sys.stderr)
        print("Dumping session data...", file=sys.stderr)

        # Get session dump for display
        session_dump = self.proton_session.dump()

        print("\nSession data to save:", file=sys.stderr)
        print(
            f"   API URL: {
                session_dump.get(
                    'api_url',
                    'N/A')}",
            file=sys.stderr,
        )
        print(
            f"   App version: {
                session_dump.get(
                    'appversion',
                    'N/A')}",
            file=sys.stderr,
        )
        if "session_data" in session_dump:
            print(
                f"   UID: {
                    session_dump['session_data'].get(
                        'UID', '')[
                        :20]}... [TRUNCATED]",
                file=sys.stderr,
            )
            print(
                f"   Scope: {
                    session_dump['session_data'].get(
                        'Scope',
                        'N/A')}",
                file=sys.stderr,
            )
        print("\nWriting to file...", file=sys.stderr)

        # Call parent method to perform the actual save
        super().save_session(filepath)

        try:
            file_size = os.path.getsize(filepath)
            print("\033[1;32mSession saved successfully\033[0m", file=sys.stderr)
            print(f"   File size: {file_size} bytes", file=sys.stderr)
        except OSError:
            print("WARNING: Could not retrieve file size", file=sys.stderr)
        print("=" * self.DEBUG_LINE_WIDTH + "\n", file=sys.stderr)

    def load_session(
        self, filepath: str, log_dir: Optional[str] = None, cache_dir: Optional[str] = None
    ) -> None:
        """Load session with debug output."""
        print("\n" + "=" * self.DEBUG_LINE_WIDTH, file=sys.stderr)
        print("\033[1;33mLOAD SESSION\033[0m", file=sys.stderr)
        print("=" * self.DEBUG_LINE_WIDTH, file=sys.stderr)
        print(f"File path: {filepath}", file=sys.stderr)

        if not os.path.exists(filepath):
            print("\033[1;31mERROR:\033[0m File not found", file=sys.stderr)
            print("=" * self.DEBUG_LINE_WIDTH + "\n", file=sys.stderr)
            raise FileNotFoundError(f"Session file not found: {filepath}")

        file_size = os.path.getsize(filepath)
        print(f"File size: {file_size} bytes", file=sys.stderr)
        print("Reading session file...", file=sys.stderr)

        # Read to show debug info
        with open(filepath, "r") as f:
            file_data = json.load(f)

        print("File loaded successfully", file=sys.stderr)

        # Handle keyring pointer file vs legacy direct dump
        session_dump = None
        if isinstance(file_data, dict) and file_data.get("storage_type") == "keyring":
            # Keyring pointer file - retrieve actual session from keychain
            print("   Storage type: keyring (secure)", file=sys.stderr)
            uid = file_data.get("uid")
            if uid:
                try:
                    stored_json = keyring.get_password("pylumo", uid)
                    if stored_json:
                        session_dump = json.loads(stored_json)
                except Exception as e:
                    print(f"   WARNING: Could not retrieve from keychain: {e}", file=sys.stderr)
        else:
            # Legacy direct dump
            print("   Storage type: file (legacy)", file=sys.stderr)
            session_dump = file_data

        print("\nSession data:", file=sys.stderr)
        if session_dump:
            print(
                f"   API URL: {session_dump.get('api_url', 'N/A')}",
                file=sys.stderr,
            )
            print(
                f"   App version: {session_dump.get('appversion', 'N/A')}",
                file=sys.stderr,
            )
            if "session_data" in session_dump:
                uid_val = session_dump['session_data'].get('UID', '')
                uid_len = len(uid_val) if uid_val else 0
                print(
                    f"   UID: {'*' * 20} [REDACTED, {uid_len} chars]",
                    file=sys.stderr,
                )
                print(
                    f"   Scope: {session_dump['session_data'].get('Scope', 'N/A')}",
                    file=sys.stderr,
                )
        else:
            print("   (Session data stored in keychain)", file=sys.stderr)

        print("\nRestoring Proton session...", file=sys.stderr)

        super().load_session(filepath, log_dir, cache_dir)

        print("\033[1;32mSession restored successfully\033[0m", file=sys.stderr)
        uid_len = len(self.proton_session.UID) if self.proton_session.UID else 0
        print(f"   UID: {'*' * 20} [REDACTED, {uid_len} chars]", file=sys.stderr)
        token_len = len(self.proton_session.AccessToken) if self.proton_session.AccessToken else 0
        print(
            f"   AccessToken: {'*' * 32} [REDACTED, {token_len} chars]",
            file=sys.stderr,
        )
        print("   Alternative routing: Disabled (direct connection)", file=sys.stderr)
        print("\nAuthenticated mode enabled", file=sys.stderr)
        print("=" * self.DEBUG_LINE_WIDTH + "\n", file=sys.stderr)

    def send_request(
        self,
        prompt: str,
        tools: Optional[List[str]] = None,
        targets: Optional[List[str]] = None,
        stream_callback: Optional[Callable[[str, str], None]] = None,
        model: Optional[str] = None,
    ) -> Dict[str, str]:
        """Send request with debug output for authentication mode and statistics."""

        # Show authentication status before request
        if self.authenticated_mode and self.proton_session:
            print("\n" + "=" * self.DEBUG_LINE_WIDTH, file=sys.stderr)
            print(
                "\033[1;32mUSING AUTHENTICATED PROTON SESSION\033[0m", file=sys.stderr
            )
            print("=" * self.DEBUG_LINE_WIDTH, file=sys.stderr)
            uid_len = len(self.proton_session.UID) if self.proton_session.UID else 0
            print(
                f"   UID: {'*' * 20} [REDACTED, {uid_len} chars]",
                file=sys.stderr,
            )

            # Show authorization header fully redacted
            if (
                hasattr(self.proton_session, "AccessToken")
                and self.proton_session.AccessToken
            ):
                token_len = len(self.proton_session.AccessToken)
                print(
                    f"   Authorization: Bearer {'*' * 32} [REDACTED, {token_len} chars]",
                    file=sys.stderr,
                )

            print("   Endpoint: /api/ai/v1/chat", file=sys.stderr)
            print("   Method: POST (streaming)", file=sys.stderr)

            # Show enabled tools
            if tools:
                tools_str = ", ".join(tools)
                print(f"   Tools: [{tools_str}]", file=sys.stderr)
            else:
                print("   Tools: [none]", file=sys.stderr)

            print("=" * self.DEBUG_LINE_WIDTH + "\n", file=sys.stderr)
        else:
            print("\n" + "=" * self.DEBUG_LINE_WIDTH, file=sys.stderr)
            print(
                "\033[1;33mUSING UNAUTHENTICATED REQUEST (GUEST MODE)\033[0m",
                file=sys.stderr,
            )
            print("=" * self.DEBUG_LINE_WIDTH, file=sys.stderr)
            print("   No Proton session active", file=sys.stderr)
            print(f"   Endpoint: {self.base_url}", file=sys.stderr)
            print("   Method: POST (streaming)", file=sys.stderr)
            print("   Authorization: None", file=sys.stderr)

            # Show enabled tools
            if tools:
                tools_str = ", ".join(tools)
                print(f"   Tools: [{tools_str}]", file=sys.stderr)
            else:
                print("   Tools: [none]", file=sys.stderr)

            print("=" * self.DEBUG_LINE_WIDTH + "\n", file=sys.stderr)

        # Create the request payload to show it in debug output
        payload, aes_key = self.create_request_payload(
            prompt, tools, targets, model
        )

        # Show the request payload structure
        print("\n" + "─" * self.DEBUG_LINE_WIDTH, file=sys.stderr)
        print("\033[1;36mREQUEST PAYLOAD\033[0m", file=sys.stderr)
        print("─" * self.DEBUG_LINE_WIDTH, file=sys.stderr)

        # Show prompt (user's message)
        print("\nUser Message:", file=sys.stderr)
        print(f"  {prompt}", file=sys.stderr)

        # Show conversation history count
        history_count = (
            len(payload["messages"]) - 1
        )  # -1 for current message
        if history_count > 0:
            print(
                f"\nConversation History: {history_count} previous turn(s)",
                file=sys.stderr,
            )

        # Show targets
        target = payload["lumo"]["target"]
        if target:
            print(f"\nTarget: {target}", file=sys.stderr)

        # Show payload structure (without showing encrypted content)
        print("\nPayload Structure:", file=sys.stderr)
        print(
            f"  - Encrypted AES key (PGP): {len(payload['lumo']['request_key'])} chars",
            file=sys.stderr,
        )
        print(f"  - Request ID: {payload['lumo']['request_id']}", file=sys.stderr)
        print(
            f"  - Number of turns: {len(payload['messages'])}",
            file=sys.stderr,
        )
        print("  - All messages encrypted: AES-256-GCM", file=sys.stderr)

        print("=" * self.DEBUG_LINE_WIDTH + "\n", file=sys.stderr)

        # Track timing for statistics
        self._request_start_time = datetime.now()
        self._timestamps_by_target = {}
        self._chunk_count_by_target = {}

        # Wrap the stream callback to track statistics
        original_callback = stream_callback

        def stats_callback(target: str, chunk: str):
            """Callback wrapper to track statistics."""
            # Track timestamps for each target
            if target not in self._timestamps_by_target:
                self._timestamps_by_target[target] = []
                self._chunk_count_by_target[target] = 0
            self._timestamps_by_target[target].append(datetime.now())
            self._chunk_count_by_target[target] += 1

            # Call original callback if provided
            if original_callback:
                original_callback(target, chunk)

        # Call parent method with wrapped callback
        response = super().send_request(
            prompt,
            tools,
            targets,
            stats_callback if stream_callback else None,
            model,
        )

        # Print statistics after request completes
        request_end_time = datetime.now()
        total_duration = (request_end_time - self._request_start_time).total_seconds()

        print("\n\033[1;33mSTATISTICS\033[0m", file=sys.stderr)
        print("─" * 40, file=sys.stderr)
        print(
            f"Total time: \033[36m{
                total_duration:.3f}s\033[0m",
            file=sys.stderr,
        )

        for target, timestamps in self._timestamps_by_target.items():
            if timestamps:
                first_token_time = (
                    timestamps[0] - self._request_start_time
                ).total_seconds()
                last_token_time = (
                    timestamps[-1] - self._request_start_time
                ).total_seconds()
                duration = (
                    last_token_time - first_token_time if len(timestamps) > 1 else 0
                )
                chunk_count = self._chunk_count_by_target.get(target, 0)
                print(
                    f"{target.title()}: "
                    f"\033[32m{chunk_count} chunks\033[0m | "
                    f"First: \033[35m{first_token_time:.3f}s\033[0m | "
                    f"Last: \033[35m{last_token_time:.3f}s\033[0m | "
                    f"Duration: \033[36m{duration:.3f}s\033[0m",
                    file=sys.stderr,
                )

        print("=" * self.DEBUG_LINE_WIDTH + "\n", file=sys.stderr)

        return response
