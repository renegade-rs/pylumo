#!/usr/bin/env python3
"""
pyLumo TUI - A terminal user interface for interacting with the Lumo Proton API
using Rich and Textual libraries.
"""

# Import modal screens and image widget
from pylumo import _pylumo_tui_modals
from pylumo import _pylumo_config
from textual.binding import Binding
from rich.text import Text
from textual.widgets import (
    Button,
    Header,
    Input,
    Markdown,
    Static,
    RichLog,
)
from textual.containers import Container, Horizontal, VerticalScroll
from textual.app import App, ComposeResult

import sys
import os
import random
import time
import io
import re
import base64
import tempfile
import traceback
import urllib.request
import urllib.error
import mimetypes
from datetime import datetime
from typing import Optional
from pathlib import Path
from io import StringIO

# Try to import PIL for image handling
try:
    from PIL import Image as PILImage

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    PILImage = None

# Import the pyLumo client
try:
    from pylumo import pylumo as pylumo_module
    from pylumo import _pylumo_debug
    from pylumo import __version__
    pyLumo = pylumo_module.pyLumo
    pyLumoDebug = _pylumo_debug.pyLumoDebug
    # Import enums for message types
    Role = pylumo_module.Role
    ResponseMessageType = pylumo_module.ResponseMessageType
    LumoTools = pylumo_module.LumoTools
    ContextLimits = pylumo_module.ContextLimits
except ImportError as e:
    print(
        "Error: Could not import pyLumo. Make sure pylumo.py and _pylumo_debug.py are available."
    )
    print(f"Import error: {e}")
    sys.exit(-1)

# ------------------------------------------------------------------------------------
# Easy aliases for modal screens
TEXTUAL_IMAGE_AVAILABLE = _pylumo_tui_modals.TEXTUAL_IMAGE_AVAILABLE
AboutModal = _pylumo_tui_modals.AboutModal
ClearChatConfirmModal = _pylumo_tui_modals.ClearChatConfirmModal
FileBrowserModal = _pylumo_tui_modals.FileBrowserModal
ImageViewModal = _pylumo_tui_modals.ImageViewModal
FilePreviewModal = _pylumo_tui_modals.FilePreviewModal
LoginModal = _pylumo_tui_modals.LoginModal
LogoutConfirmModal = _pylumo_tui_modals.LogoutConfirmModal
TwoFactorModal = _pylumo_tui_modals.TwoFactorModal
QuitConfirmModal = _pylumo_tui_modals.QuitConfirmModal
SaveChatModal = _pylumo_tui_modals.SaveChatModal
SaveDebugModal = _pylumo_tui_modals.SaveDebugModal
SplashScreenModal = _pylumo_tui_modals.SplashScreenModal
ToolsModal = _pylumo_tui_modals.ToolsModal
Image = _pylumo_tui_modals.Image
ConfigManager = _pylumo_config.ConfigManager

# ASCII Cat Faces
CAT_ASCIIS = [
    # 1. Classic Cat
    "  /\\_/\\\n ( o.o )\n  > ^ <",
    # 2. Happy Cat
    "  /\\_/\\\n ( ^.^ )\n  > ♥ <",
    # 3. Grumpy Cat
    "  /\\_/\\\n ( -.- )\n  > < <",
    # 4. Winking Cat
    "  /\\_/\\\n ( ^.o )\n  > ~ <",
    # 5. Surprised Cat
    "  /\\_/\\\n ( O.O )\n  > ∆ <",
    # 6. Sleepy Cat
    "  /\\_/\\\n ( -.- )\n  > υ <",
    # 7. Zoomy Cat
    "  /\\_/\\\n ( ◕.◕ )\n  > ω <",
    # 8. Cool Cat
    "  /\\_/\\\n ( ⊙.⊙ )\n  > ▼ <",
    # 9. Curious Cat
    "  /\\_/\\\n ( °.° )\n  > ◇ <",
    # 10. Playful Cat
    "  /\\_/\\\n ( •.• )\n  > ▽ <",
]

# Cat Emojis for file attachments
CAT_EMOJIS = ["🐱", "😺", "😸", "😹", "😻", "😼", "😽", "🙀", "😿", "😾"]

# Walking paw prints frames for spinner
CAT_PAW_PRINTS = [
    "[bold #9d4edd]Lumo[/] [dim #ffd60a]is thinking[/] [#9d4edd]🐾[/]     ",
    "[bold #9d4edd]Lumo[/] [dim #ffd60a]is thinking[/]  [#9d4edd]🐾[/]    ",
    "[bold #9d4edd]Lumo[/] [dim #ffd60a]is thinking[/]   [#9d4edd]🐾[/]   ",
    "[bold #9d4edd]Lumo[/] [dim #ffd60a]is thinking[/]    [#9d4edd]🐾[/]  ",
    "[bold #9d4edd]Lumo[/] [dim #ffd60a]is thinking[/]     [#9d4edd]🐾[/] ",
    "[bold #9d4edd]Lumo[/] [dim #ffd60a]is thinking[/]    [#9d4edd]🐾[/]  ",
    "[bold #9d4edd]Lumo[/] [dim #ffd60a]is thinking[/]   [#9d4edd]🐾[/]   ",
    "[bold #9d4edd]Lumo[/] [dim #ffd60a]is thinking[/]  [#9d4edd]🐾[/]    ",
]
# ------------------------------------------------------------------------------------


class PyLumoTUI(App):
    """A Textual TUI application for pyLumo chat interface."""

    # Load CSS from external file
    CSS_PATH = "_pylumo_tui.tcss"

    BINDINGS = [
        Binding(
            "ctrl+x", "clear", "Clear Chat", show=True, key_display="^X", priority=True
        ),
        Binding(
            "ctrl+s", "save_chat", "Save", show=True, key_display="^S", priority=True
        ),
        Binding(
            "ctrl+u",
            "upload_file",
            "Upload",
            show=True,
            key_display="^U",
            priority=True,
        ),
        Binding(
            "f2", "toggle_debug", "Debug", show=True, key_display="F2", priority=True
        ),
        Binding(
            "f10",
            "save_debug",
            "Save Debug",
            show=True,
            key_display="F10",
            priority=True,
        ),
        Binding(
            "f1", "show_about", "About", show=True, key_display="F1", priority=True
        ),
        Binding("ctrl+l", "login", "Login", show=True, key_display="^L", priority=True),
        Binding(
            "ctrl+k", "logout", "Logout", show=True, key_display="^K", priority=True
        ),
        Binding("ctrl+q", "quit", "Quit", show=True, key_display="^Q", priority=True),
        Binding("ctrl+c", "quit", "Quit", show=False, priority=True),
        Binding(
            "ctrl+backslash", "command_palette", show=True
        ),  # Disable default ctrl+p
    ]

    TITLE = "pyLumo TUI"
    SUB_TITLE = f"Brought to you by the cool cats at Mindgard - https://mindgard.ai - [ver. {__version__}]"

    @staticmethod
    def _get_secure_app_dir() -> Path:
        """Get secure application directory based on platform.

        Returns platform-appropriate directory:
        - Linux and macOS: ~/.local/share/pylumo
        - Windows: %APPDATA%/pylumo
        """
        if sys.platform == "win32":  # Windows
            base_dir = Path(
                os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
            )
        else:  # Linux, macOS and others
            base_dir = Path.home() / ".local" / "share"

        app_dir = base_dir / "pylumo"
        app_dir.mkdir(parents=True, exist_ok=True, mode=0o700)  # Owner-only permissions
        return app_dir

    def _save_tools_config(self) -> None:
        """Save the current tool selection to configuration."""
        self.config.set_enabled_tools(self.enabled_tools)

    def _load_tools_config(self) -> None:
        """Load saved tool selection from configuration."""
        saved_tools = self.config.get_enabled_tools()
        # Validate that saved tools are valid
        valid_tools = [
            "proton_info",
            "web_search",
            "stock",
            "weather",
            "cryptocurrency",
        ]
        if saved_tools and all(tool in valid_tools for tool in saved_tools):
            self.enabled_tools = saved_tools

    def _save_username_config(self, username: str) -> None:
        """Save the username to configuration."""
        self.config.set_username(username)

    def _load_username_config(self) -> str:
        """Load saved username from configuration."""
        return self.config.get_username()

    def __init__(self):
        super().__init__()
        self.client: Optional[pyLumo] = None
        self.is_processing = False
        self.uploaded_files: list[str] = []  # List of file paths to upload
        # Map file paths to their cat emojis
        self.file_cat_emojis: dict[str, str] = {}
        self.debug_panel_visible = False
        self.original_stderr = sys.stderr
        self.stderr_capture = None
        self.message_history: list[dict] = []  # Store raw message history
        # Track when loading started
        self.loading_start_time: Optional[float] = None
        self.enabled_tools: list[str] = ["proton_info"]  # Default enabled tools
        self.splash_shown = False  # Track if splash screen has been shown
        self._temp_files: list[str] = []  # Track temp files for cleanup on exit

        # Use secure application directory
        self.app_dir = self._get_secure_app_dir()
        self.log_dir = str(self.app_dir / "logs")
        self.cache_dir = str(self.app_dir / "cache")
        self.tmp_dir = str(self.app_dir / "tmp")

        # Initialize unified config manager
        self.config = ConfigManager(self.app_dir)

        # Session file path (pyLumo client manages the actual session data)
        self.session_file = str(self.app_dir / "session.json")

        # Create subdirectories with secure permissions
        Path(self.log_dir).mkdir(parents=True, exist_ok=True, mode=0o700)
        Path(self.cache_dir).mkdir(parents=True, exist_ok=True, mode=0o700)
        Path(self.tmp_dir).mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.chmod(self.tmp_dir, 0o700)
        except Exception:
            pass

        # Load saved tool preferences
        self._load_tools_config()

        # Load saved username
        self.saved_username = self._load_username_config()

        self.authenticated = False

    def compose(self) -> ComposeResult:
        """Create the UI layout."""
        yield Header()
        with Horizontal(id="main-container"):
            # Add 'hidden' class to content-container initially to prevent flash before splash screen
            with Container(
                id="content-container",
                classes="hidden" if not self.splash_shown else "",
            ):
                yield ChatContainer(id="chat-container")
                with Horizontal(id="status-container"):
                    yield StatusBar(id="status-bar")
                    yield TokenCounter(id="token-counter")
                yield Horizontal(id="file-list-container")
                with Horizontal(id="input-container"):
                    yield Input(
                        placeholder="Type your message here...",
                        id="prompt-input",
                    )
                    yield Button("Send", variant="primary", id="send-button")
                    yield Button("Upload", variant="default", id="upload-button")
                    yield Button("Tools", variant="default", id="tools-button")
            yield DebugPanel(id="debug-panel")
        yield CustomFooter()

    def on_mount(self) -> None:
        """Show splash screen immediately on mount."""
        # Show splash screen first, before any initialization
        splash_image_path = os.path.join(os.path.dirname(__file__), "_purp_cat.png")

        def on_splash_dismiss(result=None):
            """Initialize app after splash screen dismisses."""
            # Remove hidden class from content container
            content_container = self.query_one("#content-container")
            content_container.remove_class("hidden")
            self.splash_shown = True
            # Initialize the app
            self._initialize_app()

        self.push_screen(
            SplashScreenModal(splash_image_path, duration=2.0), on_splash_dismiss
        )

    def _initialize_app(self) -> None:
        """Initialize the application components."""

        # Set up stderr capture
        def stderr_callback(text):
            """Callback to handle stderr output."""
            try:
                debug_panel = self.query_one("#debug-panel", DebugPanel)
                debug_panel.add_debug_line(text)
            except Exception:
                pass

        self.stderr_capture = StderrCapture(stderr_callback, self.original_stderr)
        sys.stderr = self.stderr_capture

        # Initialize the pyLumo client (use Debug version for stderr output)
        # Set skip_2fa_prompt=True so TUI can handle 2FA with modal
        try:
            self.client = pyLumoDebug(quiet_mode=False, skip_2fa_prompt=True)

            # Try to load saved session
            if os.path.exists(self.session_file):
                try:
                    self.client.load_session(self.session_file)
                    self.authenticated = True
                    self.query_one("#status-bar", StatusBar).update_status(
                        "Authenticated session loaded", "success"
                    )

                    # Update footer to show logout button
                    footer = self.query_one(CustomFooter)
                    footer.update_auth_buttons()
                except Exception as e:
                    print(f"Failed to load session: {e}", file=sys.stderr)
                    self.query_one("#status-bar", StatusBar).update_status(
                        "Connected (Guest Mode) - Press ^L to login", "idle"
                    )
            else:
                self.query_one("#status-bar", StatusBar).update_status(
                    "Connected (Guest Mode) - Press ^L to login", "idle"
                )

            # Add welcome message
            chat = self.query_one("#chat-container", ChatContainer)
            if self.authenticated:
                welcome_msg = f"Welcome back! You're already authenticated with Proton. Loaded session from: {
                    self.session_file}"
                self.message_history.append(
                    {
                        "role": "system",
                        "content": welcome_msg,
                        "timestamp": datetime.now(),
                    }
                )
                chat.add_message("system", welcome_msg)

                greeting = (
                    "Hello! I'm Lumo, your AI assistant. How can I help you today?"
                )
                self.message_history.append(
                    {
                        "role": "assistant",
                        "content": greeting,
                        "timestamp": datetime.now(),
                    }
                )
                chat.add_message("assistant", greeting)
            else:
                welcome_msg = "Welcome to the pyLumo TUI! You're in Guest Mode. Press ^L to login with your Proton account for authenticated access."
                self.message_history.append(
                    {
                        "role": "assistant",
                        "content": welcome_msg,
                        "timestamp": datetime.now(),
                    }
                )
                chat.add_message("assistant", welcome_msg)
        except Exception as e:
            self.query_one("#status-bar", StatusBar).update_status(
                f"Error initializing client: {e}", "error"
            )

        # Focus on input
        self.query_one("#prompt-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "send-button":
            self.handle_send()
        elif event.button.id == "upload-button":
            self.action_upload_file()
        elif event.button.id == "tools-button":
            self.action_select_tools()
        elif event.button.id and event.button.id.startswith("remove-file-"):
            # Extract file index from the button's classes
            button = event.button
            # Find the file-idx-N class
            for css_class in button.classes:
                if css_class.startswith("file-idx-"):
                    try:
                        idx = int(css_class.replace("file-idx-", ""))
                        if 0 <= idx < len(self.uploaded_files):
                            removed_file = self.uploaded_files.pop(idx)
                            # Also remove the cat emoji mapping for this file
                            if removed_file in self.file_cat_emojis:
                                del self.file_cat_emojis[removed_file]
                            self.update_file_list()
                            self.query_one("#status-bar", StatusBar).update_status(
                                f"Removed: {
                                    os.path.basename(removed_file)}",
                                "success",
                            )
                        break
                    except ValueError:
                        pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission (Enter key)."""
        if event.input.id == "prompt-input":
            self.handle_send()

    def handle_send(self) -> None:
        """Handle sending a message - display user message immediately."""
        if self.is_processing:
            return

        prompt_input = self.query_one("#prompt-input", Input)
        prompt = prompt_input.value.strip()

        if not prompt:
            return

        # Clear input immediately
        prompt_input.value = ""

        # Store user message in history
        self.message_history.append(
            {"role": "user", "content": prompt, "timestamp": datetime.now()}
        )

        # Add user message to chat immediately with file attachments
        chat = self.query_one("#chat-container", ChatContainer)
        chat.add_message(
            "user",
            prompt,
            files=self.uploaded_files.copy() if self.uploaded_files else None,
        )

        # Add loading indicator and track start time
        self.loading_start_time = time.time()
        chat.add_loading_indicator()

        # Update status
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.update_status("Sending request to Lumo...", "working")

        # Mark as processing
        self.is_processing = True

        # Force a refresh to show the user message before API call
        self.refresh()

        # Run the API call in a worker (use call_later to ensure UI updates
        # first)
        self.call_later(self._start_api_call, prompt)

    def _start_api_call(self, prompt: str) -> None:
        """Start the API call in a worker."""
        self.run_worker(self.send_message(prompt), exclusive=True, thread=True)

    async def send_message(self, prompt: str) -> None:
        """Send a message to the Lumo API."""
        try:
            # Call the API (blocking call runs in thread due to thread=True)
            if not self.client:
                raise RuntimeError("Client not initialized")

            # Append file uploads to the prompt if any
            combined_prompt = prompt
            if self.uploaded_files:
                for file_path in self.uploaded_files:
                    try:
                        file_content = self.client.format_file_upload(file_path)
                        combined_prompt += f"\n\n{file_content}"
                    except Exception as e:
                        # Log error but continue
                        self.call_from_thread(
                            self.query_one("#status-bar", StatusBar).update_status,
                            f"Error uploading {file_path}: {e}",
                            "error",
                        )

                # Clear uploaded files after sending
                self.uploaded_files.clear()
                self.call_from_thread(self.update_file_list)

            # Track if we've started streaming (to remove loading indicator on
            # first chunk)
            streaming_started = False

            # Use streaming callback to update UI in real-time
            def stream_callback(target: str, chunk: str):
                nonlocal streaming_started
                if target == "message":
                    # Start streaming on first chunk (removes loading
                    # indicator)
                    if not streaming_started:
                        streaming_started = True
                        self.call_from_thread(self._start_streaming_response)
                    self.call_from_thread(self._append_streaming_chunk, chunk)

            # Use user-selected tools
            response = self.client.send_request(
                prompt=combined_prompt,
                tools=self.enabled_tools,
                targets=["title", "message"],
                stream_callback=stream_callback,
            )

            # Finalize the streaming response with all response data
            message_content = response.get("message", "")
            tool_call_content = response.get("tool_call")
            tool_result_content = response.get("tool_result")
            error_type = response.get("_error")  # Error type if any

            self.call_from_thread(
                self._finalize_streaming_response,
                message_content,
                tool_call_content,
                tool_result_content,
                error_type
            )

        except Exception as e:
            self.call_from_thread(self._display_error, str(e))

    def _display_response(self, message_content: str) -> None:
        """Display the API response (called from main thread)."""
        chat = self.query_one("#chat-container", ChatContainer)
        status_bar = self.query_one("#status-bar", StatusBar)
        prompt_input = self.query_one("#prompt-input", Input)

        # Remove loading indicator
        chat.remove_loading_indicator()

        if message_content:
            chat.add_message("assistant", message_content)
            status_bar.update_status("Response received", "success")
        else:
            chat.add_message("assistant", "[No response received]")
            status_bar.update_status("Empty response", "error")

        self.is_processing = False
        prompt_input.focus()

    def _display_error(self, error_msg: str) -> None:
        """Display an error message (called from main thread)."""
        chat = self.query_one("#chat-container", ChatContainer)
        status_bar = self.query_one("#status-bar", StatusBar)
        prompt_input = self.query_one("#prompt-input", Input)

        # Remove loading indicator
        chat.remove_loading_indicator()

        chat.add_message("assistant", f"[Error: {error_msg}]")
        status_bar.update_status(f"Error: {error_msg}", "error")

        self.is_processing = False
        prompt_input.focus()

    def _start_streaming_response(self) -> None:
        """Start a streaming response (called from main thread)."""

        # Ensure loading indicator is visible for at least 1 second
        if self.loading_start_time:
            elapsed = time.time() - self.loading_start_time
            min_display_time = 1.0  # seconds
            if elapsed < min_display_time:
                remaining = min_display_time - elapsed
                # Schedule the removal after the remaining time
                self.set_timer(remaining, lambda: self._continue_streaming_response())
                return

        # If enough time has passed, continue immediately
        self._continue_streaming_response()

    def _continue_streaming_response(self) -> None:
        """Continue with streaming response after minimum display time."""
        chat = self.query_one("#chat-container", ChatContainer)

        # Remove loading indicator
        chat.remove_loading_indicator()
        self.loading_start_time = None

        # Start a streaming message
        chat.start_streaming_message()

    def _append_streaming_chunk(self, chunk: str) -> None:
        """Append a chunk to the streaming message (called from main thread)."""
        chat = self.query_one("#chat-container", ChatContainer)
        chat.append_streaming_chunk(chunk)

    def _finalize_streaming_response(
        self,
        full_message: str,
        tool_call: Optional[str] = None,
        tool_result: Optional[str] = None,
        error_type: Optional[str] = None
    ) -> None:
        """Finalize the streaming response (called from main thread).

        Args:
            full_message: The complete assistant message content
            tool_call: Optional tool call data (JSON string)
            tool_result: Optional tool result data
            error_type: Optional error type if the response had an error
        """
        chat = self.query_one("#chat-container", ChatContainer)
        status_bar = self.query_one("#status-bar", StatusBar)
        prompt_input = self.query_one("#prompt-input", Input)

        # Store assistant message in history with all metadata
        history_entry = {
            "role": "assistant",
            "content": full_message,
            "timestamp": datetime.now(),
        }

        # Add optional tool data if present
        if tool_call:
            history_entry["tool_call"] = tool_call
        if tool_result:
            history_entry["tool_result"] = tool_result
        if error_type:
            history_entry["error_type"] = error_type

        self.message_history.append(history_entry)

        # Finalize the streaming message
        chat.finalize_streaming_message(full_message)

        # Update token counter
        self._update_token_counter()

        # Update status based on whether there was an error
        if error_type:
            status_bar.update_status(f"Completed with error: {error_type}", "error")
        else:
            status_bar.update_status("Ready", "idle")

        self.is_processing = False
        prompt_input.focus()

    def _update_token_counter(self) -> None:
        """Update the token counter widget with current conversation token count."""
        try:
            if self.client:
                token_count = self.client.get_conversation_token_count()
                token_counter = self.query_one("#token-counter", TokenCounter)
                token_counter.update_tokens(token_count)
        except Exception:
            pass  # Ignore errors if widget not found

    def _cleanup_temp_files(self) -> None:
        """Clean up all tracked temporary files."""
        for temp_path in self._temp_files:
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except OSError:
                pass  # Ignore errors during cleanup
        self._temp_files.clear()

    def action_clear(self) -> None:
        """Clear the chat history with confirmation."""

        def handle_clear_confirm(confirmed: bool) -> None:
            """Handle the clear confirmation result."""
            if confirmed:
                chat = self.query_one("#chat-container", ChatContainer)
                # Remove all message bubbles
                chat.remove_children()

                # Clear message history
                self.message_history.clear()

                # Add welcome message back
                welcome_msg = "Chat cleared. How can I help you?"
                self.message_history.append(
                    {
                        "role": "assistant",
                        "content": welcome_msg,
                        "timestamp": datetime.now(),
                    }
                )
                chat.add_message("assistant", welcome_msg)

                # Also clear conversation history in the client
                if self.client:
                    self.client.clear_conversation_history()

                # Reset token counter
                self._update_token_counter()

                self.query_one("#status-bar", StatusBar).update_status(
                    "Chat cleared", "success"
                )

        self.push_screen(ClearChatConfirmModal(), handle_clear_confirm)

    def action_save_chat(self) -> None:
        """Save chat history to a Markdown file using message history buffer."""

        def handle_save(filename: Optional[str]) -> None:
            """Handle the save result."""
            if not filename:
                return

            try:
                md_content = [
                    "# pyLumo Chat Session",
                    f"**Saved:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    "---",
                ]

                # Use the message history buffer instead of extracting from
                # widgets
                for msg in self.message_history:
                    role = msg["role"]
                    content = msg.get("content", "")
                    timestamp = msg["timestamp"].strftime("%H:%M:%S")

                    # Get optional tool data
                    tool_call = msg.get("tool_call")
                    tool_result = msg.get("tool_result")
                    error_type = msg.get("error_type")

                    # Set role emoji and name based on role type
                    # Handle both string roles and Role enum values
                    role_str = role.value if hasattr(role, 'value') else role

                    if role_str == "user" or role_str == Role.USER.value:
                        role_emoji = "👤"
                        role_name = "User"
                    elif role_str == "assistant" or role_str == Role.ASSISTANT.value:
                        role_emoji = "🤖"
                        role_name = "Assistant"
                    elif role_str == "system" or role_str == Role.SYSTEM.value:
                        role_emoji = "⚙️"
                        role_name = "System"
                    elif role_str == "tool_call" or role_str == Role.TOOL_CALL.value:
                        role_emoji = "🔧"
                        role_name = "Tool Call"
                    elif role_str == "tool_result" or role_str == Role.TOOL_RESULT.value:
                        role_emoji = "📋"
                        role_name = "Tool Result"
                    elif role_str == "error":
                        role_emoji = "❌"
                        role_name = "Error"
                    elif role_str == "status":
                        role_emoji = "ℹ️"
                        role_name = "Status"
                    else:
                        role_emoji = "❓"
                        role_name = role_str.title() if isinstance(role_str, str) else "Unknown"

                    # Add message to markdown
                    md_content.append(f"### {role_emoji} {role_name}")
                    md_content.append(f"*{timestamp}*")
                    md_content.append("")

                    # Add main content
                    if content:
                        md_content.append(content)

                    # Add tool call details if present
                    if tool_call:
                        md_content.append("")
                        md_content.append("**🔧 Tool Call:**")
                        md_content.append("```json")
                        md_content.append(tool_call)
                        md_content.append("```")

                    # Add tool result details if present
                    if tool_result:
                        md_content.append("")
                        md_content.append("**📋 Tool Result:**")
                        md_content.append("```")
                        md_content.append(tool_result)
                        md_content.append("```")

                    # Add error type if present
                    if error_type:
                        md_content.append("")
                        md_content.append(f"**Error Type:** `{error_type}`")

                    md_content.append("---")

                # Write to file
                with open(filename, "w", encoding="utf-8") as f:
                    f.write("\n\n".join(md_content))

                try:
                    os.chmod(filename, 0o600)
                except Exception:
                    pass

                self.query_one("#status-bar", StatusBar).update_status(
                    f"Chat saved to {filename}", "success"
                )
            except Exception as e:
                self.query_one("#status-bar", StatusBar).update_status(
                    f"Error saving chat: {e}", "error"
                )

        self.push_screen(SaveChatModal(), handle_save)

    def action_show_about(self) -> None:
        """Show the about modal."""
        self.push_screen(AboutModal(__version__))

    def action_login(self) -> None:
        """Show login modal to authenticate with Proton."""

        def handle_login(credentials: Optional[dict]) -> None:
            """Handle login credentials from modal."""
            if not credentials:
                return  # User cancelled

            email = credentials["email"]
            password = credentials["password"]
            remember_me = credentials.get(
                "remember_me", True
            )  # Default to True if not present

            # Show loading indicator in chat
            chat = self.query_one("#chat-container", ChatContainer)
            status_bar = self.query_one("#status-bar", StatusBar)

            chat.add_message(
                "system",
                "Authenticating with Proton...",
            )
            chat.add_loading_indicator()
            status_bar.update_status("Authenticating...", "info")

            # Define the authentication work
            def do_auth(remember_session: bool):
                try:
                    # Get TLS pinning setting from config
                    tls_pinning = self.config.get_tls_pinning()

                    # Authenticate with Proton using secure directories
                    session_info = self.client.authenticate_with_proton(
                        username=email,
                        password=password,
                        log_dir=self.log_dir,
                        cache_dir=self.cache_dir,
                        tls_pinning=tls_pinning,
                    )

                    # Check if 2FA is required (debug class returns this in
                    # session_info)
                    if session_info.get("TwoFactorRequired"):
                        # 2FA is required - show modal from UI thread
                        twofa_info = session_info.get("TwoFactorInfo", {})
                        self.call_from_thread(on_twofa_required, twofa_info)
                        return  # Don't complete auth yet

                    # No 2FA needed, save session if requested
                    if remember_session:
                        self.client.save_session(self.session_file)
                    self.call_from_thread(on_auth_success, email, remember_session)

                except Exception as e:
                    # Print detailed error information to stderr (debug panel)
                    print("\n" + "=" * 78, file=sys.stderr)
                    print("AUTHENTICATION ERROR", file=sys.stderr)
                    print("=" * 78, file=sys.stderr)
                    print(f"Error Type: {type(e).__name__}", file=sys.stderr)
                    print(f"Error Message: {str(e)}", file=sys.stderr)
                    print("\nFull Traceback:", file=sys.stderr)
                    print("-" * 78, file=sys.stderr)
                    traceback.print_exc(file=sys.stderr)
                    print("=" * 78 + "\n", file=sys.stderr)
                    # Update UI from worker thread
                    self.call_from_thread(on_auth_failure, str(e))

            # Success callback
            def on_auth_success(email_addr, session_saved: bool):
                # Remove loading indicator
                chat.remove_loading_indicator()

                # Success
                self.authenticated = True
                status_bar.update_status("Authenticated with Proton", "success")

                # Save username for future logins
                self._save_username_config(email_addr)

                # Update footer to show logout button
                footer = self.query_one(CustomFooter)
                footer.update_auth_buttons()

                # Add confirmation message to chat
                if session_saved:
                    chat.add_message(
                        "system",
                        f"Successfully authenticated as {email_addr}. Your session has been saved.",
                    )
                else:
                    chat.add_message(
                        "system",
                        f"Successfully authenticated as {email_addr}. Your session will not be saved.",
                    )

            # Failure callback
            def on_auth_failure(error_msg):
                # Remove loading indicator
                chat.remove_loading_indicator()

                # Failure
                status_bar.update_status(f"Authentication failed: {error_msg}", "error")

                # Add error message to chat
                chat.add_message(
                    "system",
                    f"Authentication failed: {error_msg}\n\nPlease try again (^L) or continue in Guest Mode.",
                )

            # 2FA required callback
            def on_twofa_required(twofa_info):
                # Remove loading indicator
                chat.remove_loading_indicator()

                # IMPORTANT: Set authenticated flag here
                # The session is partially authenticated (has tokens, limited scope)
                # This ensures authenticated API calls are used
                self.authenticated = True

                # Update status
                status_bar.update_status("2FA verification required", "info")

                # Add message to chat
                chat.add_message(
                    "system",
                    "Two-factor authentication is required for your account.\nPlease enter your 2FA code to continue.",
                )

                # Show 2FA modal
                def handle_twofa(code: Optional[str]) -> None:
                    """Handle 2FA code from modal."""
                    if not code:
                        # User cancelled
                        status_bar.update_status("Authentication cancelled", "idle")
                        chat.add_message(
                            "system",
                            "Authentication cancelled. You can try again (^L) or continue in Guest Mode.",
                        )
                        return

                    # Show loading indicator
                    chat.add_message("system", "Verifying 2FA code...")
                    chat.add_loading_indicator()
                    status_bar.update_status("Verifying 2FA...", "info")

                    # Verify 2FA in worker thread
                    def do_twofa_verify():
                        try:
                            self.client.proton_session.provide_2fa(code)

                            # Save session if requested
                            if remember_me:
                                self.client.save_session(self.session_file)

                            # Success
                            self.call_from_thread(on_auth_success, email, remember_me)
                        except Exception as e:
                            # Print detailed error information to stderr (debug panel)
                            print("\n" + "=" * 78, file=sys.stderr)
                            print("2FA VERIFICATION ERROR", file=sys.stderr)
                            print("=" * 78, file=sys.stderr)
                            print(f"Error Type: {type(e).__name__}", file=sys.stderr)
                            print(f"Error Message: {str(e)}", file=sys.stderr)
                            print("\nFull Traceback:", file=sys.stderr)
                            print("-" * 78, file=sys.stderr)
                            traceback.print_exc(file=sys.stderr)
                            print("=" * 78 + "\n", file=sys.stderr)
                            self.call_from_thread(on_twofa_failure, str(e))

                    self.run_worker(do_twofa_verify, exit_on_error=False, thread=True)

                self.push_screen(
                    TwoFactorModal(available_methods=twofa_info), handle_twofa
                )

            # 2FA failure callback
            def on_twofa_failure(error_msg):
                # Remove loading indicator
                chat.remove_loading_indicator()

                # Failure
                status_bar.update_status(
                    f"2FA verification failed: {error_msg}", "error"
                )

                # Add error message to chat
                chat.add_message(
                    "system",
                    f"2FA verification failed: {error_msg}\n\nPlease try logging in again (^L).",
                )

            # Run authentication in worker thread, using a lambda to pass the
            # argument
            self.run_worker(
                lambda: do_auth(remember_session=remember_me),
                exit_on_error=False,
                thread=True,
            )

        self.push_screen(LoginModal(saved_username=self.saved_username), handle_login)

    def action_logout(self) -> None:
        """Show confirmation modal before logging out."""
        if not self.authenticated:
            # Not logged in, nothing to do
            status_bar = self.query_one("#status-bar", StatusBar)
            status_bar.update_status("Not logged in", "idle")
            return

        def handle_logout_confirm(confirmed: bool) -> None:
            """Handle the logout confirmation result."""
            if not confirmed:
                return  # User cancelled

            try:
                # Logout from Proton API
                if self.client and self.client.proton_session:
                    self.client.logout()

                # Remove saved session file and keychain entry
                if self.client:
                    self.client.delete_saved_session(self.session_file)

                # Update state
                self.authenticated = False

                # Update status bar
                status_bar = self.query_one("#status-bar", StatusBar)
                status_bar.update_status("Logged out (Guest Mode)", "idle")

                # Update footer to show login button
                footer = self.query_one(CustomFooter)
                footer.update_auth_buttons()

                # Add message to chat
                chat = self.query_one("#chat-container", ChatContainer)
                chat.add_message(
                    "system",
                    "Successfully logged out. Session cleared. You're now in Guest Mode.\n\nPress ^L to login again.",
                )
            except Exception as e:
                status_bar = self.query_one("#status-bar", StatusBar)
                status_bar.update_status(f"Logout error: {str(e)}", "error")

        # Show confirmation modal
        self.push_screen(LogoutConfirmModal(), handle_logout_confirm)

    def action_upload_file(self) -> None:
        """Open file browser to select a file for upload."""

        def handle_file_selection(file_path: Optional[str]) -> None:
            """Handle the file selection result."""
            if file_path:
                # Add file to upload list if not already present
                if file_path not in self.uploaded_files:
                    self.uploaded_files.append(file_path)
                    self.update_file_list()
                    self.query_one("#status-bar", StatusBar).update_status(
                        f"File added: {file_path}", "success"
                    )
                else:
                    self.query_one("#status-bar", StatusBar).update_status(
                        f"File already added: {file_path}", "idle"
                    )

        self.push_screen(FileBrowserModal(), handle_file_selection)

    def action_select_tools(self) -> None:
        """Open tools selection modal."""

        def handle_tools_selection(selected_tools: Optional[list]) -> None:
            """Handle the tools selection result."""
            if selected_tools is not None:
                self.enabled_tools = selected_tools
                self._save_tools_config()
                tools_str = ", ".join(selected_tools)
                self.query_one("#status-bar", StatusBar).update_status(
                    f"Tools updated: {tools_str}", "success"
                )

        self.push_screen(ToolsModal(self.enabled_tools), handle_tools_selection)

    def update_file_list(self) -> None:
        """Update the file list display."""
        file_list_container = self.query_one("#file-list-container", Horizontal)

        # Remove all existing children first
        children = list(file_list_container.children)
        for child in children:
            child.remove()

        # Add file items
        if self.uploaded_files:
            for idx, file_path in enumerate(self.uploaded_files):
                filename = os.path.basename(file_path)
                # Get or assign a cat emoji for this file (persistent)
                if file_path not in self.file_cat_emojis:
                    self.file_cat_emojis[file_path] = random.choice(CAT_EMOJIS)
                cat_emoji = self.file_cat_emojis[file_path]
                # Create a button for each file so it's clickable
                # Use a timestamp-based unique ID to avoid conflicts
                unique_id = f"remove-file-{idx}-{int(time.time() * 1000000)}"
                file_button = Button(
                    f"{cat_emoji} {filename} ✕",
                    variant="default",
                    id=unique_id,
                    classes=f"file-item file-idx-{idx}",
                )
                file_list_container.mount(file_button)

    def action_save_debug(self) -> None:
        """Save debug output to a file including message history and context status."""

        def handle_save(filename: Optional[str]) -> None:
            """Handle the save result."""
            if filename:
                try:
                    # Get debug panel
                    debug_panel = self.query_one("#debug-panel", DebugPanel)
                    debug_log = debug_panel.query_one("#debug-log", RichLog)

                    # Extract text content from the debug log
                    debug_content = []
                    debug_content.append("=" * 80)
                    debug_content.append("pyLumo Debug Output")
                    debug_content.append(
                        f"Saved: {
                            datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    debug_content.append("=" * 80)
                    debug_content.append("")

                    # Add context status if client is available
                    if self.client:
                        try:
                            context_status = self.client.get_context_status()
                            debug_content.append("CONTEXT WINDOW STATUS")
                            debug_content.append("-" * 40)
                            debug_content.append(f"Token Count: {context_status['token_count']}")
                            debug_content.append(f"Usage: {context_status['usage_percent']:.1f}%")
                            debug_content.append(f"Warning Level: {context_status['warning_level']}")
                            debug_content.append(f"Max Context: {context_status['max_context']}")
                            debug_content.append("")
                        except Exception:
                            pass

                    # Add message history summary
                    debug_content.append("MESSAGE HISTORY SUMMARY")
                    debug_content.append("-" * 40)
                    debug_content.append(f"Total messages: {len(self.message_history)}")

                    # Count message types
                    role_counts = {}
                    tool_call_count = 0
                    tool_result_count = 0
                    error_count = 0

                    for msg in self.message_history:
                        role = msg.get("role", "unknown")
                        role_str = role.value if hasattr(role, 'value') else role
                        role_counts[role_str] = role_counts.get(role_str, 0) + 1
                        if msg.get("tool_call"):
                            tool_call_count += 1
                        if msg.get("tool_result"):
                            tool_result_count += 1
                        if msg.get("error_type"):
                            error_count += 1

                    for role, count in sorted(role_counts.items()):
                        debug_content.append(f"  {role}: {count}")

                    if tool_call_count > 0:
                        debug_content.append(f"  (with tool_call data): {tool_call_count}")
                    if tool_result_count > 0:
                        debug_content.append(f"  (with tool_result data): {tool_result_count}")
                    if error_count > 0:
                        debug_content.append(f"  (with errors): {error_count}")

                    debug_content.append("")
                    debug_content.append("=" * 80)
                    debug_content.append("DEBUG LOG OUTPUT")
                    debug_content.append("=" * 80)
                    debug_content.append("")

                    # Get the lines from the RichLog and extract plain text
                    # Render all lines in the log, extracting plain text
                    for line in debug_log.lines:
                        # Each line is a Strip object containing Segments
                        # Extract plain text by concatenating segment text
                        if hasattr(line, "__iter__"):
                            # Strip is iterable, contains Segment objects
                            plain_text = ""
                            for segment in line:
                                if hasattr(segment, "text"):
                                    plain_text += segment.text
                            debug_content.append(plain_text)
                        elif hasattr(line, "text"):
                            # If it has a text attribute, use it directly
                            debug_content.append(line.text)
                        else:
                            # Fallback: convert to string
                            debug_content.append(str(line))

                    # Add detailed message history at the end
                    debug_content.append("")
                    debug_content.append("=" * 80)
                    debug_content.append("DETAILED MESSAGE HISTORY")
                    debug_content.append("=" * 80)

                    for i, msg in enumerate(self.message_history):
                        role = msg.get("role", "unknown")
                        role_str = role.value if hasattr(role, 'value') else role
                        content = msg.get("content", "")
                        timestamp = msg.get("timestamp", datetime.now()).strftime("%H:%M:%S")

                        debug_content.append("")
                        debug_content.append(f"[{i+1}] {role_str.upper()} @ {timestamp}")
                        debug_content.append("-" * 40)

                        # Truncate long content for debug output
                        if len(content) > 500:
                            debug_content.append(content[:500] + "... [truncated]")
                        else:
                            debug_content.append(content if content else "(empty)")

                        # Add tool data if present
                        if msg.get("tool_call"):
                            debug_content.append("")
                            debug_content.append("  TOOL_CALL:")
                            tool_call_preview = msg["tool_call"][:200] if len(msg["tool_call"]) > 200 else msg["tool_call"]
                            debug_content.append(f"    {tool_call_preview}")

                        if msg.get("tool_result"):
                            debug_content.append("")
                            debug_content.append("  TOOL_RESULT:")
                            tool_result_preview = msg["tool_result"][:200] if len(msg["tool_result"]) > 200 else msg["tool_result"]
                            debug_content.append(f"    {tool_result_preview}")

                        if msg.get("error_type"):
                            debug_content.append("")
                            debug_content.append(f"  ERROR_TYPE: {msg['error_type']}")

                    # Write to file
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write("\n".join(debug_content))

                    try:
                        os.chmod(filename, 0o600)
                    except Exception:
                        pass

                    self.query_one("#status-bar", StatusBar).update_status(
                        f"Debug output saved to {filename}", "success"
                    )
                except Exception as e:
                    self.query_one("#status-bar", StatusBar).update_status(
                        f"Error saving debug output: {e}", "error"
                    )

        self.push_screen(SaveDebugModal(), handle_save)

    def action_toggle_debug(self) -> None:
        """Toggle the debug panel visibility."""
        if not self.debug_panel_visible:
            # Create stderr capture if not exists
            if self.stderr_capture is None:
                self.stderr_capture = StringIO()
                # Redirect stderr to capture
                sys.stderr = self.stderr_capture

            # Show debug panel
            debug_panel = self.query_one("#debug-panel", DebugPanel)
            debug_panel.styles.width = "40%"
            debug_panel.add_class("visible")
            self.debug_panel_visible = True
            self.query_one("#status-bar", StatusBar).update_status(
                "Debug panel opened", "success"
            )
        else:
            # Hide debug panel
            debug_panel = self.query_one("#debug-panel", DebugPanel)
            debug_panel.styles.width = 0
            debug_panel.remove_class("visible")
            self.debug_panel_visible = False
            self.query_one("#status-bar", StatusBar).update_status(
                "Debug panel closed", "idle"
            )

    def action_quit(self) -> None:
        """Quit the application with confirmation."""

        def handle_quit_response(should_quit: bool) -> None:
            """Handle the quit confirmation response."""
            if should_quit:
                # Clean up temporary files
                self._cleanup_temp_files()
                # Restore original stderr
                if self.stderr_capture:
                    sys.stderr = self.original_stderr
                self.exit()

        # Show confirmation modal
        self.push_screen(QuitConfirmModal(), handle_quit_response)


class LoadingIndicator(Static):
    """Animated loading indicator widget with walking paw prints."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.frame = 0
        self.frames = CAT_PAW_PRINTS

    def on_mount(self) -> None:
        """Start the animation when mounted."""
        self.update(self.frames[0])
        self.set_interval(0.2, self.animate)

    def animate(self) -> None:
        """Update the animation frame."""
        self.frame = (self.frame + 1) % len(self.frames)
        self.update(self.frames[self.frame])


class ChatContainer(VerticalScroll):
    """Container for chat messages."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.streaming_content = ""  # Track streaming content

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press for image view buttons and file preview buttons."""
        if hasattr(event.button, "image_path"):
            # This is an image button - open the image modal
            image_path = event.button.image_path
            # Get alt text stored on button
            alt_text = getattr(event.button, "alt_text", "")
            tmp_dir = getattr(self.app, "tmp_dir", None)
            self.app.push_screen(ImageViewModal(image_path, alt_text, tmp_dir=tmp_dir))
            event.stop()  # Stop event propagation
        elif hasattr(event.button, "file_path"):
            # This is a file preview button - open the file preview modal
            file_path = event.button.file_path
            self.app.push_screen(FilePreviewModal(file_path))
            event.stop()  # Stop event propagation

    def add_message(
        self, role: str, content: str, files: Optional[list[str]] = None
    ) -> None:
        """Add a message to the chat."""
        timestamp = datetime.now().strftime("%H:%M:%S")

        if role == "user":
            # User messages: yellow background
            message_text = (
                f"[bold #ffd60a]You[/] [dim #9d4edd]{timestamp}[/]\n{content}"
            )
            message_widget = Static(" " + message_text, classes="message user-message")
            self.mount(message_widget)

            # Add file attachment buttons if any
            if files:
                self._render_file_attachments(files)
        elif role == "system":
            # System messages: cyan/blue for authentication/system events
            message_text = (
                f"[bold #00d9ff]System[/] [dim #9d4edd]{timestamp}[/]\n{content}"
            )
            message_widget = Static(
                " " + message_text, classes="message system-message"
            )
            self.mount(message_widget)
        else:
            # Assistant messages: purple accents with random cat face
            cat_face = random.choice(CAT_ASCIIS)

            # Check if content looks like markdown (has markdown indicators)
            is_markdown = self._is_markdown(content)

            # Add header first
            header_text = f" [bold #9d4edd]Lumo[/] [dim #ffd60a]{timestamp}[/]\n\n[#9d4edd]{cat_face}[/]"
            header_widget = Static(
                header_text, classes="message assistant-message message-header"
            )
            self.mount(header_widget)

            if is_markdown:
                # Check for embedded images if textual-image is available
                if TEXTUAL_IMAGE_AVAILABLE and self._has_images(content):
                    # Render markdown with images
                    self._render_markdown_with_images(content)
                else:
                    # Add markdown widget without image support
                    markdown_widget = Markdown(
                        content, classes="message assistant-message message-markdown"
                    )
                    self.mount(markdown_widget)
            else:
                # Plain text message
                text_widget = Static(
                    " " + content, classes="message assistant-message message-content"
                )
                self.mount(text_widget)

        # Auto-scroll to bottom
        self.scroll_end(animate=False)

    def _is_markdown(self, text: str) -> bool:
        """Check if text contains markdown formatting."""
        markdown_indicators = [
            "```",  # Code blocks
            "##",  # Headers
            "**",  # Bold
            "__",  # Bold/Italic
            "* ",  # Lists
            "- ",  # Lists
            "1. ",  # Numbered lists
            "[",  # Links
            "|",  # Tables
        ]
        return any(indicator in text for indicator in markdown_indicators)

    def _has_images(self, text: str) -> bool:
        """Check if markdown text contains image references."""
        # Match markdown image syntax: ![alt](path)
        image_pattern = r"!\[([^\]]*)\]\(([^\)]+)\)"
        return bool(re.search(image_pattern, text))

    def _render_markdown_with_images(self, content: str) -> None:
        """Render markdown content with embedded images."""
        # Pattern to match markdown images: ![alt](path)
        image_pattern = r"!\[([^\]]*)\]\(([^\)]+)\)"

        # Split content by images
        parts = re.split(image_pattern, content)

        # Collect widgets to add to container
        widgets = []

        i = 0
        while i < len(parts):
            if i % 3 == 0:
                # Regular text/markdown content
                if parts[i].strip():
                    markdown_widget = Markdown(parts[i])
                    widgets.append(markdown_widget)
            elif i % 3 == 2:
                # Image path (parts[i-1] is alt text, parts[i] is path)
                image_path = parts[i].strip()
                alt_text = parts[i - 1] if i > 0 else ""

                # Check if this is a valid image reference
                is_valid_image = False

                # Check for data URI (base64 embedded image)
                if image_path.startswith("data:image/"):
                    is_valid_image = True
                # Check for HTTP/HTTPS URL
                elif image_path.startswith(("http://", "https://")):
                    is_valid_image = True
                # Check for local file that exists
                elif os.path.exists(image_path):
                    is_valid_image = True

                if is_valid_image and PIL_AVAILABLE:
                    # Render image inline
                    try:
                        # Handle different image sources
                        if image_path.startswith("data:image/"):
                            # Decode data URI
                            temp_path = self._decode_data_uri_inline(image_path)
                            pil_image = PILImage.open(temp_path)
                            image_widget = Image(pil_image, classes="inline-image")
                        elif image_path.startswith(("http://", "https://")):
                            # Download URL
                            temp_path = self._download_url_inline(image_path)
                            pil_image = PILImage.open(temp_path)
                            image_widget = Image(pil_image, classes="inline-image")
                        else:
                            # Local file
                            pil_image = PILImage.open(image_path)
                            image_widget = Image(pil_image, classes="inline-image")

                        # Prevent image from taking focus
                        image_widget.can_focus = False
                        widgets.append(image_widget)
                    except Exception as e:
                        # Fallback to button if inline rendering fails
                        print(
                            f"[DEBUG] Inline image failed: {e}",
                            file=sys.stderr,
                        )
                        button_label = f"🖼️  View Image: {
                                alt_text or os.path.basename(image_path)}"
                        image_button = Button(
                            button_label,
                            variant="default",
                            classes="image-view-button",
                        )
                        image_button.can_focus = False
                        image_button.image_path = image_path
                        image_button.alt_text = alt_text
                        widgets.append(image_button)
                else:
                    # Image reference but file not accessible
                    # Show as informational text instead of error
                    info_text = Static(
                        f"[dim #9d4edd]🖼️  {
                            alt_text or 'Image'}[/] [dim](reference: {
                            os.path.basename(image_path)})[/]"
                    )
                    widgets.append(info_text)

            i += 1

        # Mount widgets directly to avoid scroll issues with nested containers
        for widget in widgets:
            self.mount(widget)

    def _render_file_attachments(self, files: list[str]) -> None:
        """Render file attachments as horizontal buttons."""
        # Create horizontal container for file buttons
        file_container = Horizontal(classes="file-attachments-container")
        self.mount(file_container)

        for file_path in files:
            filename = os.path.basename(file_path)
            # Determine file type icon
            ext = os.path.splitext(filename)[1].lower()
            if ext in [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"]:
                icon = "🖼️"
            elif ext in [
                ".txt",
                ".md",
                ".py",
                ".js",
                ".json",
                ".yaml",
                ".yml",
                ".toml",
                ".ini",
                ".cfg",
                ".conf",
            ]:
                icon = "📄"
            elif ext in [".pdf"]:
                icon = "📕"
            elif ext in [".zip", ".tar", ".gz", ".7z", ".rar"]:
                icon = "📦"
            else:
                icon = "📎"

            # Create button for file preview
            file_button = Button(
                f"{icon} {filename}",
                variant="default",
                classes="file-preview-button",
            )
            file_button.can_focus = False
            file_button.file_path = file_path
            file_container.mount(file_button)

    def _decode_data_uri_inline(self, data_uri: str) -> str:
        """Decode a data URI and save to a temporary file for inline display."""
        # Parse data URI: data:image/jpeg;base64,<data>
        match = re.match(r"data:image/([^;]+);base64,(.+)", data_uri)
        if not match:
            raise ValueError("Invalid data URI format")

        image_format = match.group(1)
        base64_data = match.group(2).strip()

        # Decode base64
        image_data = base64.b64decode(base64_data)

        # Create temporary file in app-owned temp directory and track for cleanup
        fd, temp_path = tempfile.mkstemp(
            prefix="pylumo-inline-",
            suffix=f".{image_format}",
            dir=self.tmp_dir,
        )
        try:
            try:
                os.fchmod(fd, 0o600)
            except Exception:
                pass
            with os.fdopen(fd, "wb") as f:
                fd = -1
                f.write(image_data)
        finally:
            if fd != -1:
                try:
                    os.close(fd)
                except Exception:
                    pass

        self._temp_files.append(temp_path)
        return temp_path

    def _download_url_inline(self, url: str) -> str:
        """Download an image from a URL to a temporary file for inline display."""
        # Create request with proper headers to avoid 403/404 errors
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": url,
            },
        )

        try:
            # Download the image
            with urllib.request.urlopen(request, timeout=10) as response:
                image_data = response.read()
                content_type = response.headers.get("Content-Type", "")

                # Check if we got HTML instead of an image
                if "text/html" in content_type:
                    raise ValueError(
                        "URL returned HTML page instead of image. This might be a wiki page or indirect link."
                    )

                extension = (
                    mimetypes.guess_extension(content_type.split(";")[0]) or ".jpg"
                )

            # Create temporary file in app-owned temp directory and track for cleanup
            fd, temp_path = tempfile.mkstemp(
                prefix="pylumo-inline-",
                suffix=extension,
                dir=self.tmp_dir,
            )
            try:
                try:
                    os.fchmod(fd, 0o600)
                except Exception:
                    pass
                with os.fdopen(fd, "wb") as f:
                    fd = -1
                    f.write(image_data)
            finally:
                if fd != -1:
                    try:
                        os.close(fd)
                    except Exception:
                        pass

            self._temp_files.append(temp_path)
            return temp_path
        except urllib.error.HTTPError as e:
            # Handle HTTP errors with more specific messages
            if e.code == 503:
                raise ValueError(
                    "Image server temporarily unavailable (503). Try again later."
                )
            elif e.code == 404:
                raise ValueError("Image not found (404). URL may be incorrect.")
            elif e.code == 403:
                raise ValueError("Access forbidden (403). Server blocked the request.")
            else:
                raise ValueError(f"HTTP Error {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            raise ValueError(f"Network error: {e.reason}")

    def add_loading_indicator(self) -> None:
        """Add an animated loading indicator to show activity."""
        loading_widget = LoadingIndicator(
            classes="message assistant-message loading-indicator",
            id="loading-indicator",
        )
        self.mount(loading_widget)
        self.scroll_end(animate=False)

    def remove_loading_indicator(self) -> None:
        """Remove the loading indicator."""
        try:
            loading = self.query_one("#loading-indicator")
            loading.remove()
        except Exception:
            pass  # Indicator already removed or doesn't exist

    def start_streaming_message(self) -> None:
        """Start a streaming message with header."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        cat_face = random.choice(CAT_ASCIIS)

        # Reset streaming content
        self.streaming_content = ""

        # Add header
        header_text = f" [bold #9d4edd]Lumo[/] [dim #ffd60a]{timestamp}[/]\n\n[#9d4edd]{cat_face}[/]"
        header_widget = Static(
            header_text, classes="message assistant-message message-header"
        )
        self.mount(header_widget)

        # Add a streaming content widget (plain text that we'll update)
        streaming_widget = Static(
            " ",
            classes="message assistant-message message-content",
            id="streaming-message",
        )
        self.mount(streaming_widget)
        self.scroll_end(animate=False)
        print("Streaming message started:", file=sys.stderr)

    def append_streaming_chunk(self, chunk: str) -> None:
        """Append a chunk to the streaming message."""
        try:
            # Show chunk with length info in parentheses, with orange color for
            # visibility
            chunk_preview = chunk[:50] + "..." if len(chunk) > 50 else chunk
            print(
                f"\t\033[38;5;208mStream chunk:\033[0m {chunk_preview} \033[90m({
                    len(chunk)} chars, total: {
                    len(
                        self.streaming_content) +
                    len(chunk)})\033[0m",
                file=sys.stderr,
            )

            streaming_widget = self.query_one("#streaming-message", Static)

            # Append to our tracked content
            self.streaming_content += chunk

            # Update the widget with the full content
            streaming_widget.update(" " + self.streaming_content)

            # Force a refresh to ensure the update is visible immediately
            streaming_widget.refresh()
            self.scroll_end(animate=False)
        except Exception as e:
            print(f"[DEBUG] Error appending chunk: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

    def finalize_streaming_message(self, full_message: str) -> None:
        """Finalize the streaming message by replacing with markdown if needed."""
        try:
            # Try to remove the streaming widget if it exists
            # We ignore errors here in case of race conditions where it wasn't created yet
            try:
                streaming_widget = self.query_one("#streaming-message", Static)
                streaming_widget.remove()
            except Exception:
                pass

            # Ensure loading indicator is removed (in case streaming never started)
            self.remove_loading_indicator()

            # Check if content looks like markdown
            is_markdown = self._is_markdown(full_message)

            if is_markdown:
                # Check for embedded images if textual-image is available
                if TEXTUAL_IMAGE_AVAILABLE and self._has_images(full_message):
                    # Render markdown with images
                    self._render_markdown_with_images(full_message)
                else:
                    # Add markdown widget without image support
                    markdown_widget = Markdown(
                        full_message,
                        classes="message assistant-message message-markdown",
                    )
                    self.mount(markdown_widget)
            else:
                # Plain text message
                text_widget = Static(
                    " " + full_message,
                    classes="message assistant-message message-content",
                )
                self.mount(text_widget)

            self.scroll_end(animate=False)
        except Exception as e:
            print(f"[DEBUG] Error finalizing message: {e}", file=sys.stderr)


class StatusBar(Static):
    """Status bar showing connection status and info."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.update_status("Ready", "idle")

    def update_status(self, message: str, status_type: str = "info") -> None:
        """Update the status bar message."""
        if status_type == "idle":
            self.update(f"[dim #9d4edd]●[/] {message}")
        elif status_type == "working":
            self.update(f"[bold #ffd60a]●[/] {message}")
        elif status_type == "error":
            self.update(f"[bold red]●[/] {message}")
        elif status_type == "success":
            self.update(f"[bold green]●[/] {message}")


class TokenCounter(Static):
    """Widget showing token usage for the current chat session."""

    DEFAULT_CSS = """
    TokenCounter {
        height: 1;
        width: auto;
        padding: 0 1;
        text-align: right;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._token_count = 0
        self._max_tokens = ContextLimits.MAX_CONTEXT
        self._update_display()

    def _update_display(self) -> None:
        """Update the token counter display with color coding."""
        # Format token counts with K suffix for readability
        if self._token_count >= 1000:
            count_str = f"{self._token_count / 1000:.1f}K"
        else:
            count_str = str(self._token_count)

        max_str = f"{self._max_tokens // 1000}K"

        # Color code based on usage level
        if self._token_count >= ContextLimits.MAX_CONTEXT:
            # Critical - red
            color = "bold red"
            icon = "🔴"
        elif self._token_count >= ContextLimits.DANGER_THRESHOLD:
            # Danger - orange
            color = "bold #ff6b35"
            icon = "🟠"
        elif self._token_count >= ContextLimits.WARNING_THRESHOLD:
            # Warning - yellow
            color = "bold #ffd60a"
            icon = "🟡"
        else:
            # Normal - dim purple
            color = "dim #9d4edd"
            icon = "Tokens"

        self.update(f" [{color}] {icon} [{color}]{count_str}[/][dim]/[/][dim #9d4edd]{max_str}[/]")

    def update_tokens(self, token_count: int) -> None:
        """Update the token count and refresh display.

        Args:
            token_count: Current token count for the conversation
        """
        self._token_count = token_count
        self._update_display()

    def reset(self) -> None:
        """Reset the token counter to zero."""
        self._token_count = 0
        self._update_display()


class StderrCapture(io.StringIO):
    """Capture stderr output and forward it to a callback only (no stderr output)."""

    def __init__(self, callback, original_stderr):
        super().__init__()
        self.callback = callback
        self.original_stderr = original_stderr

    def write(self, text):
        # Only send to callback, don't write to original stderr
        if text.strip():
            self.callback(text)
        return len(text)

    def flush(self):
        # No-op since we're not writing to original stderr
        pass


class DebugPanel(Container):
    """Debug panel showing stderr output."""

    DEFAULT_CSS = """
    DebugPanel {
        width: 0;
        height: 100%;
        background: #0a0a0a;
        border-left: thick #9d4edd;
        overflow: hidden hidden;
    }

    DebugPanel.visible {
        width: 33%;
    }

    DebugPanel RichLog {
        background: #0a0a0a;
        border: none;
        height: 100%;
    }

    DebugPanel #debug-panel-title {
        dock: top;
        height: 3;
    }
    """

    def compose(self) -> ComposeResult:
        """Create the debug panel content."""
        yield Static("[bold #9d4edd]Debug Output (stderr)[/]", id="debug-panel-title")
        yield RichLog(id="debug-log", highlight=True, markup=True, wrap=True)

    def on_mount(self) -> None:
        """Initialize debug panel with ANSI art cat logo."""
        try:
            log = self.query_one("#debug-log", RichLog)

            # ANSI art purple cat using block characters and ANSI codes
            # Using ANSI escape codes for purple (magenta) color
            bold_purple = "\033[1;35m"  # Bold Magenta
            reset = "\033[0m"

            # Debug Cat
            debug_cat = [
                "      ╱|、",
                "    (˚ˎ 。7",
                "     |、˜〵",
                "    じしˍ,)ノ",
            ]

            log.write("")
            log.write(Text("═" * 40, style="#9d4edd", justify="center"))
            log.write("")

            # Write each line centered with ANSI color
            for cat_slice in debug_cat:
                colored_cat_slice = f"{bold_purple}{cat_slice}{reset}"
                log.write(Text.from_ansi(colored_cat_slice, justify="center"))

            # Add title
            log.write("")
            log.write(
                Text(
                    "pyLumo TUI Debug Window",
                    style="bold #9d4edd",
                    justify="center",
                )
            )
            log.write("")
            log.write(Text("═" * 40, style="#9d4edd", justify="center"))
            log.write("")
        except Exception:
            pass  # Panel might not be fully mounted yet

    def add_debug_line(self, text: str) -> None:
        """Add a line to the debug log with ANSI color support."""
        try:
            log = self.query_one("#debug-log", RichLog)
            # RichLog automatically handles ANSI codes when markup=False
            # We need to use the Text object from Rich to preserve ANSI codes
            # Create a Text object from the ANSI string
            rich_text = Text.from_ansi(text.rstrip())
            log.write(rich_text)
        except Exception:
            pass  # Panel might not be mounted yet


class FooterItem(Static):
    """A clickable footer item."""

    def __init__(self, label: str, action: str, **kwargs):
        super().__init__(label, **kwargs)
        self.action_name = action
        self.can_focus = True

    def on_click(self) -> None:
        """Handle click on footer item."""
        # Call the action method on the app
        action_method = getattr(self.app, f"action_{self.action_name}", None)
        if action_method:
            action_method()


class CustomFooter(Horizontal):
    """Custom footer with clickable key bindings."""

    DEFAULT_CSS = """
    CustomFooter {
        background: $panel;
        color: $text;
        dock: bottom;
        height: 1;
        padding: 0 1;
    }

    FooterItem {
        width: auto;
        height: 1;
        padding: 0 1;
        background: transparent;
        color: $text;
    }

    FooterItem:hover {
        background: $accent;
        text-style: bold;
    }
    """

    def compose(self) -> ComposeResult:
        """Create clickable footer items."""
        yield FooterItem("^Q Quit", "quit", id="footer-quit")
        yield FooterItem("^L Login", "login", id="footer-login")
        yield FooterItem("^K Logout", "logout", id="footer-logout")
        yield FooterItem("^U Upload File", "upload_file", id="footer-upload")
        yield FooterItem("^X Clear Chat", "clear", id="footer-clear")
        yield FooterItem("^S Save Chat", "save_chat", id="footer-save")
        yield FooterItem("F2 Debug Panel", "toggle_debug", id="footer-debug")
        yield FooterItem("F10 Save Debug", "save_debug", id="footer-save-debug")
        yield FooterItem("F1 About", "show_about", id="footer-about")

    def on_mount(self) -> None:
        """Update footer based on authentication state."""
        self.update_auth_buttons()

    def update_auth_buttons(self) -> None:
        """Show/hide login/logout buttons based on authentication state."""
        try:
            app = self.app
            if isinstance(app, PyLumoTUI):
                login_button = self.query_one("#footer-login", FooterItem)
                logout_button = self.query_one("#footer-logout", FooterItem)

                if app.authenticated:
                    # Show logout, hide login
                    login_button.display = False
                    logout_button.display = True
                else:
                    # Show login, hide logout
                    login_button.display = True
                    logout_button.display = False
        except Exception:
            pass  # Ignore if buttons not found yet


def main() -> None:
    """Run the TUI application."""
    app = PyLumoTUI()
    app.run()


if __name__ == "__main__":
    main()
