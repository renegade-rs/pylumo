"""
Modal screens for pyLumo TUI.

This module contains all modal dialog screens used in the pyLumo TUI application.
"""
from pylumo import __version__

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Button, Checkbox, DirectoryTree, Input, Static
from textual.screen import ModalScreen

# Try to import textual-image for embedded image support
try:
    from textual_image.widget import AutoImage, Image

    TEXTUAL_IMAGE_AVAILABLE = True
except ImportError:
    TEXTUAL_IMAGE_AVAILABLE = False
    AutoImage = None
    Image = None


class FileBrowserModal(ModalScreen[str]):
    """Modal screen for browsing and selecting files."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self):
        super().__init__()
        self.current_path = os.path.abspath("./")

    def compose(self) -> ComposeResult:
        """Create the file browser interface."""
        with Container(id="file-browser-dialog"):
            yield Static(
                "[bold #9d4edd]Select a File to Upload[/]",
                id="file-browser-title",
            )
            # Show hidden files by setting show_hidden=True
            tree = DirectoryTree(self.current_path, id="file-tree")
            tree.show_hidden = True
            yield tree

            # Add directory navigation section
            yield Static(
                "Navigate to directory:",
                id="dir-nav-label",
            )
            with Horizontal(id="dir-nav-container"):
                yield Input(
                    placeholder="Enter directory path...",
                    value=self.current_path,
                    id="dir-path-input",
                )
                yield Button("Go", variant="default", id="go-dir-button")

            yield Static("", id="dir-nav-status")

            with Horizontal(id="file-browser-buttons"):
                yield Button("Select", variant="primary", id="select-file-button")
                yield Button("Cancel", variant="default", id="cancel-file-button")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "select-file-button":
            tree = self.query_one("#file-tree", DirectoryTree)
            if tree.cursor_node and tree.cursor_node.data:
                # DirEntry object - check if it's a file using is_file() method
                # (no parens for DirEntry)
                try:
                    # DirEntry.is_file() is a method that needs to be called
                    file_path = tree.cursor_node.data.path
                    if os.path.isfile(file_path):
                        self.dismiss(str(file_path))
                    else:
                        # Directory selected - show error or do nothing
                        pass
                except Exception:
                    # Error accessing file
                    pass
            else:
                # No selection
                pass
        elif event.button.id == "cancel-file-button":
            self.dismiss(None)
        elif event.button.id == "go-dir-button":
            self._navigate_to_directory()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in directory input."""
        if event.input.id == "dir-path-input":
            self._navigate_to_directory()

    def _navigate_to_directory(self) -> None:
        """Navigate to the directory specified in the input."""
        dir_input = self.query_one("#dir-path-input", Input)
        status = self.query_one("#dir-nav-status", Static)
        new_path = dir_input.value.strip()

        if not new_path:
            status.update("[red]Please enter a directory path[/]")
            return

        # Expand user home directory
        new_path = os.path.expanduser(new_path)

        # Convert to absolute path
        if not os.path.isabs(new_path):
            new_path = os.path.abspath(new_path)

        # Check if directory exists
        if not os.path.exists(new_path):
            status.update(f"[red]Directory does not exist: {new_path}[/]")
            return

        if not os.path.isdir(new_path):
            status.update(f"[red]Not a directory: {new_path}[/]")
            return

        # Update the tree with new directory
        try:
            self.current_path = new_path

            # Get the existing tree
            tree = self.query_one("#file-tree", DirectoryTree)

            # Update the tree's path property to reload it
            tree.path = self.current_path
            tree.reload()

            # Update input to show canonical path
            dir_input.value = self.current_path
            status.update(f"[green]Navigated to: {self.current_path}[/]")

        except Exception as e:
            status.update(f"[red]Error navigating to directory: {str(e)}[/]")

    def action_cancel(self) -> None:
        """Cancel file selection."""
        self.dismiss(None)


class AboutModal(ModalScreen):
    """Modal screen displaying information about pyLumo."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
    ]

    def __init__(self, version: str = "0.0.1"):
        super().__init__()
        self.version = version

    def compose(self) -> ComposeResult:
        """Create the modal content."""
        with Container(id="about-dialog"):
            yield Static(
                "[bold #9d4edd]pyLumo[/] [dim #ffd60a]TUI[/]",
                id="about-title",
            )
            yield Static(
                f"[bold #ffd60a]brought to you by the cool cats at Mindgard.ai[/]\nVer: {self.version}",
                id="about-subtitle",
            )
            yield Static(
                "A secure terminal interface for Proton's Lumo AI assistant with end-to-end "
                "encryption and real-time streaming.\n\n"
                "[bold]Current Features:[/]\n"
                "• Guest mode and authenticated Proton sessions\n"
                "• 2FA support in the TUI (prompted when required)\n"
                "• Secure session storage via OS keychain (no tokens saved in plaintext files)\n"
                "• End-to-end encryption (AES-256-GCM + PGP)\n"
                "• Real-time streaming responses\n"
                "• Tool selection (e.g. Proton info, web search, weather, stock, crypto)\n"
                "• File upload support with directory navigation\n"
                "• Attachment preview (text + images when optional dependencies are installed)\n"
                "• Debug panel with request/response inspection + export\n"
                "• Context/token counter to help manage long conversations\n\n"
                "[bold]Links:[/]\n"
                "• GitHub: https://github.com/Mindgard/pylumo\n"
                "• Lumo Web App: https://lumo.proton.me\n"
                "• Mindgard: https://mindgard.ai\n\n"
                "[dim]Press ESC or click Close to return to chat[/]",
                id="about-content",
            )
            yield Button("Close", variant="primary", id="close-button")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "close-button":
            self.dismiss()

    def action_dismiss(self) -> None:
        """Dismiss the modal."""
        self.dismiss()


class QuitConfirmModal(ModalScreen[bool]):
    """Modal screen to confirm quit action."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        """Create the confirmation dialog."""
        with Container(id="quit-confirm-dialog"):
            yield Static(
                "[bold #ffd60a]Confirm Quit[/]",
                id="quit-confirm-title",
            )
            yield Static(
                "\nAre you sure you want to quit?\n\n"
                "[dim]Press ESC or Enter to cancel[/]",
                id="quit-confirm-content",
            )
            with Horizontal(id="quit-confirm-buttons"):
                yield Button("Quit", variant="default", id="confirm-quit-button")
                yield Button("Cancel", variant="primary", id="cancel-quit-button")

    def on_mount(self) -> None:
        """Focus the Cancel button when modal opens."""
        self.query_one("#cancel-quit-button", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "confirm-quit-button":
            self.dismiss(True)  # User confirmed quit
        elif event.button.id == "cancel-quit-button":
            self.dismiss(False)  # User cancelled

    def action_cancel(self) -> None:
        """Cancel quit action."""
        self.dismiss(False)


class ClearChatConfirmModal(ModalScreen[bool]):
    """Modal screen to confirm clear chat action."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        """Create the confirmation dialog."""
        with Container(id="clear-confirm-dialog"):
            yield Static(
                "[bold #ffd60a]Confirm Clear Chat[/]",
                id="clear-confirm-title",
            )
            yield Static(
                "\nAre you sure you want to clear the chat history?\n"
                "This action cannot be undone.\n\n"
                "[dim]Press ESC or Enter to cancel[/]",
                id="clear-confirm-content",
            )
            with Horizontal(id="clear-confirm-buttons"):
                yield Button("Clear", variant="default", id="confirm-clear-button")
                yield Button("Cancel", variant="primary", id="cancel-clear-button")

    def on_mount(self) -> None:
        """Focus the Cancel button when modal opens."""
        self.query_one("#cancel-clear-button", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "confirm-clear-button":
            self.dismiss(True)  # User confirmed clear
        elif event.button.id == "cancel-clear-button":
            self.dismiss(False)  # User cancelled

    def action_cancel(self) -> None:
        """Cancel clear action."""
        self.dismiss(False)


class LogoutConfirmModal(ModalScreen[bool]):
    """Modal screen to confirm logout action."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        """Create the confirmation dialog."""
        with Container(id="logout-confirm-dialog"):
            yield Static(
                "[bold #ffd60a]Confirm Logout[/]",
                id="logout-confirm-title",
            )
            yield Static(
                "\nAre you sure you want to logout?\n"
                "Your session will be cleared.\n\n"
                "[dim]Press ESC or Enter to cancel[/]",
                id="logout-confirm-content",
            )
            with Horizontal(id="logout-confirm-buttons"):
                yield Button("Logout", variant="default", id="confirm-logout-button")
                yield Button("Cancel", variant="primary", id="cancel-logout-button")

    def on_mount(self) -> None:
        """Focus the Cancel button when modal opens."""
        self.query_one("#cancel-logout-button", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "confirm-logout-button":
            self.dismiss(True)  # User confirmed logout
        elif event.button.id == "cancel-logout-button":
            self.dismiss(False)  # User cancelled

    def action_cancel(self) -> None:
        """Cancel logout action."""
        self.dismiss(False)


class SaveChatModal(ModalScreen[str]):
    """Modal screen to save chat to a file."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        """Create the save dialog."""
        # Generate default filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"pylumo_chat_{timestamp}.md"

        with Container(id="save-chat-dialog"):
            yield Static(
                "[bold #9d4edd]Save Chat[/]",
                id="save-chat-title",
            )
            yield Static(
                "\nEnter filename to save chat history:\n",
                id="save-chat-content",
            )
            yield Input(
                value=default_filename,
                placeholder="filename.md",
                id="save-filename-input",
            )
            with Horizontal(id="save-chat-buttons"):
                yield Button("Save", variant="primary", id="save-file-button")
                yield Button("Cancel", variant="default", id="cancel-save-button")

    def on_mount(self) -> None:
        """Focus the input when modal opens."""
        self.query_one("#save-filename-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "save-file-button":
            filename_input = self.query_one("#save-filename-input", Input)
            filename = filename_input.value.strip()
            if filename:
                self.dismiss(filename)
            else:
                # Don't dismiss if filename is empty
                pass
        elif event.button.id == "cancel-save-button":
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input."""
        if event.input.id == "save-filename-input":
            filename = event.input.value.strip()
            if filename:
                self.dismiss(filename)

    def action_cancel(self) -> None:
        """Cancel save action."""
        self.dismiss(None)


class SaveDebugModal(ModalScreen[str]):
    """Modal screen to save debug output to a file."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        """Create the save debug dialog."""
        # Generate default filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"pylumo_debug_{timestamp}.log"

        with Container(id="save-debug-dialog"):
            yield Static(
                "[bold #9d4edd]Save Debug Output[/]",
                id="save-debug-title",
            )
            yield Static(
                "\nEnter filename to save debug output:\n",
                id="save-debug-content",
            )
            yield Input(
                value=default_filename,
                placeholder="filename.log",
                id="save-debug-filename-input",
            )
            with Horizontal(id="save-debug-buttons"):
                yield Button("Save", variant="primary", id="save-debug-file-button")
                yield Button("Cancel", variant="default", id="cancel-debug-save-button")

    def on_mount(self) -> None:
        """Focus the input when modal opens."""
        self.query_one("#save-debug-filename-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "save-debug-file-button":
            filename_input = self.query_one("#save-debug-filename-input", Input)
            filename = filename_input.value.strip()
            if filename:
                self.dismiss(filename)
            else:
                # Don't dismiss if filename is empty
                pass
        elif event.button.id == "cancel-debug-save-button":
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input."""
        if event.input.id == "save-debug-filename-input":
            filename = event.input.value.strip()
            if filename:
                self.dismiss(filename)

    def action_cancel(self) -> None:
        """Cancel save action."""
        self.dismiss(None)


class FilePreviewModal(ModalScreen):
    """Modal screen to preview a file."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
    ]

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path

    def compose(self) -> ComposeResult:
        """Create the file preview dialog."""
        filename = os.path.basename(self.file_path)
        ext = os.path.splitext(filename)[1].lower()

        with Container(id="file-preview-dialog"):
            yield Static(
                f"[bold #9d4edd]📎 {filename}[/]",
                id="file-preview-title",
            )

            # Determine file type and render accordingly
            if ext in [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"]:
                # Image file - render using Image widget
                if TEXTUAL_IMAGE_AVAILABLE:
                    try:
                        with VerticalScroll(id="file-preview-scroll"):
                            from PIL import Image as PILImage

                            pil_image = PILImage.open(self.file_path)
                            yield Image(pil_image, id="file-preview-image")
                    except Exception as e:
                        yield Static(
                            f"[red]⚠️  Error loading image:[/]\n{str(e)}",
                            id="file-preview-error",
                        )
                else:
                    yield Static(
                        "[yellow]⚠️  textual-image not installed[/]\n\n"
                        "Install with: pip install textual-image",
                        id="file-preview-error",
                    )
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
                ".log",
                ".csv",
                ".html",
                ".css",
                ".xml",
            ]:
                # Text file - render content with syntax highlighting if
                # possible
                try:
                    with open(self.file_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    with VerticalScroll(id="file-preview-scroll"):
                        # Use RichLog for better text display with potential
                        # syntax highlighting
                        from textual.widgets import RichLog

                        log = RichLog(
                            id="file-preview-text",
                            highlight=True,
                            markup=False,
                            wrap=True,
                        )
                        yield log
                        # Add content after yielding
                        self.call_after_refresh(lambda: log.write(content))
                except Exception as e:
                    yield Static(
                        f"[red]⚠️  Error reading file:[/]\n{str(e)}",
                        id="file-preview-error",
                    )
            else:
                # Unsupported file type
                try:
                    file_size = os.path.getsize(self.file_path)
                    size_str = f"{file_size:,} bytes"
                    if file_size > 1024:
                        size_str = f"{file_size / 1024:.1f} KB"
                    if file_size > 1024 * 1024:
                        size_str = f"{file_size / (1024 * 1024):.1f} MB"

                    yield Static(
                        f"[yellow]File Type:[/] {ext or 'Unknown'}\n"
                        f"[yellow]Size:[/] {size_str}\n"
                        f"[yellow]Path:[/] {self.file_path}\n\n"
                        "[dim]Preview not available for this file type[/]",
                        id="file-preview-info",
                    )
                except Exception as e:
                    yield Static(
                        f"[red]⚠️  Error accessing file:[/]\n{str(e)}",
                        id="file-preview-error",
                    )

            yield Button("Close", variant="primary", id="close-preview-button")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "close-preview-button":
            self.dismiss()

    def action_dismiss(self) -> None:
        """Dismiss the modal."""
        self.dismiss()


class ImageViewModal(ModalScreen):
    """Modal screen to view an image."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
    ]

    def __init__(self, image_path: str, alt_text: str = "", tmp_dir: Optional[str] = None):
        super().__init__()
        self.image_path = image_path
        self.alt_text = alt_text
        self.temp_file_path = None  # Store temp file path for cleanup
        self.tmp_dir = tmp_dir

    def _get_secure_tmp_dir(self) -> str:
        if self.tmp_dir:
            tmp_path = Path(self.tmp_dir)
        else:
            if sys.platform == "win32":
                base_dir = Path(
                    os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
                )
            else:
                base_dir = Path.home() / ".local" / "share"

            tmp_path = base_dir / "pylumo" / "tmp"

        tmp_path.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.chmod(tmp_path, 0o700)
        except Exception:
            pass
        return str(tmp_path)

    def compose(self) -> ComposeResult:
        """Create the image viewer dialog."""
        with Container(id="image-view-dialog"):
            yield Static(
                f"[bold #9d4edd]🖼️  {self.alt_text or 'Image'}[/]",
                id="image-view-title",
            )

            if TEXTUAL_IMAGE_AVAILABLE:
                try:
                    # Prepare the image file path
                    if self.image_path.startswith("data:image/"):
                        # Decode data URI and save to temp file
                        image_file_path = self._decode_data_uri(self.image_path)
                    elif self.image_path.startswith(("http://", "https://")):
                        # Download URL to temp file (avoids 403 and other HTTP
                        # errors)
                        image_file_path = self._download_url_image(self.image_path)
                    else:
                        # Local file path
                        image_file_path = self.image_path

                    # Create scrollable container for the image
                    with VerticalScroll(id="image-scroll-container"):
                        # Create image widget using PIL Image (works better
                        # than AutoImage)
                        try:
                            from PIL import Image as PILImage

                            pil_image = PILImage.open(image_file_path)
                            yield Image(pil_image, id="image-display")
                        except Exception:
                            # Fallback to AutoImage if PIL fails
                            yield AutoImage(image_file_path, id="image-display")

                except Exception as e:
                    print(f"[DEBUG] Exception in compose: {e}", file=sys.stderr)
                    yield Static(
                        f"[red]⚠️  Error loading image:[/]\n{str(e)}",
                        id="image-error",
                    )
            else:
                yield Static(
                    "[yellow]⚠️  textual-image not installed[/]\n\n"
                    f"Image type: {'Data URI' if self.image_path.startswith('data:') else 'File/URL'}\n\n"
                    "Install with: pip install textual-image",
                    id="image-error",
                )

            yield Button("Close", variant="primary", id="close-image-button")

    def _decode_data_uri(self, data_uri: str) -> str:
        """Decode a data URI and save to a temporary file."""
        import base64
        import re

        # Parse data URI: data:image/jpeg;base64,<data>
        match = re.match(r"data:image/([^;]+);base64,(.+)", data_uri)
        if not match:
            raise ValueError("Invalid data URI format")

        image_format = match.group(1)  # e.g., 'jpeg', 'png'
        base64_data = match.group(2).strip()

        # Decode base64
        image_data = base64.b64decode(base64_data)

        tmp_dir = self._get_secure_tmp_dir()
        fd, temp_path = tempfile.mkstemp(suffix=f".{image_format}", dir=tmp_dir)
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

        self.temp_file_path = temp_path
        return temp_path

    def _download_url_image(self, url: str) -> str:
        """Download an image from a URL to a secure temporary file."""
        import urllib.request
        import urllib.error
        import mimetypes

        # Create request with proper headers to avoid 403 errors
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

                # Try to determine file extension from Content-Type header
                content_type = response.headers.get("Content-Type", "")

                # Check if we got HTML instead of an image
                if "text/html" in content_type:
                    raise ValueError(
                        "URL returned HTML page instead of image. This might be a wiki page or indirect link."
                    )

                extension = mimetypes.guess_extension(content_type.split(";")[0])

                # Fallback to common image extensions
                if not extension:
                    extension = ".jpg"

            tmp_dir = self._get_secure_tmp_dir()
            fd, temp_path = tempfile.mkstemp(suffix=extension, dir=tmp_dir)
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

            self.temp_file_path = temp_path
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

    def on_unmount(self) -> None:
        """Clean up temporary file when modal is closed."""
        if self.temp_file_path:
            try:
                os.unlink(self.temp_file_path)
            except Exception:
                pass  # Ignore cleanup errors

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "close-image-button":
            self.dismiss()

    def action_dismiss(self) -> None:
        """Dismiss the modal."""
        self.dismiss()


class LoginModal(ModalScreen[dict]):
    """Modal screen for Proton account login."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, saved_username: str = "", **kwargs):
        super().__init__(**kwargs)
        self.status_message = ""
        self.saved_username = saved_username

    def compose(self) -> ComposeResult:
        """Create the login interface."""
        with Container(id="login-dialog"):
            yield Static(
                "[bold #9d4edd]Login to Proton Account[/]",
                id="login-title",
            )
            yield Static(
                "Authenticate with your Proton credentials to enable authenticated mode.\n"
                "Your session will be saved for future use.",
                id="login-description",
            )

            yield Static("Email:", classes="login-label")
            yield Input(
                placeholder="your_email@proton.me",
                value=self.saved_username,
                id="login-email",
            )

            yield Static("Password:", classes="login-label")
            yield Input(
                placeholder="Enter your password",
                password=True,
                id="login-password",
            )

            yield Checkbox("Remember me", value=True, id="remember-me-checkbox")

            yield Static("", id="login-status")

            with Horizontal(id="login-buttons"):
                yield Button("Login", variant="primary", id="login-button")
                yield Button("Cancel", variant="default", id="cancel-login-button")

    def on_mount(self) -> None:
        """Focus the appropriate input when modal opens."""
        if self.saved_username:
            # If username is pre-filled, focus on password
            self.query_one("#login-password", Input).focus()
        else:
            # Otherwise focus on email
            self.query_one("#login-email", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "login-button":
            self.action_login()
        elif event.button.id == "cancel-login-button":
            self.action_cancel()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input fields."""
        if event.input.id == "login-email":
            # Move to password field
            self.query_one("#login-password", Input).focus()
        elif event.input.id == "login-password":
            # Submit the form
            self.action_login()

    def action_login(self) -> None:
        """Attempt to login with provided credentials."""
        email_input = self.query_one("#login-email", Input)
        password_input = self.query_one("#login-password", Input)
        status_widget = self.query_one("#login-status", Static)

        email = email_input.value.strip()
        password = password_input.value

        # Validate inputs
        if not email:
            status_widget.update("[red]⚠ Please enter your email address[/]")
            email_input.focus()
            return

        if not password:
            status_widget.update("[red]⚠ Please enter your password[/]")
            password_input.focus()
            return

        # Return credentials to the app
        remember_me_checkbox = self.query_one("#remember-me-checkbox", Checkbox)
        self.dismiss(
            {
                "email": email,
                "password": password,
                "remember_me": remember_me_checkbox.value,
            }
        )

    def action_cancel(self) -> None:
        """Cancel login."""
        self.dismiss(None)


class TwoFactorModal(ModalScreen[str]):
    """Modal screen for Two-Factor Authentication code input."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    # Center the modal on screen
    DEFAULT_CSS = """
    TwoFactorModal {
        align: center middle;
    }
    """

    def __init__(self, available_methods: dict = None, **kwargs):
        super().__init__(**kwargs)
        self.available_methods = available_methods or {}
        self.status_message = ""

    def compose(self) -> ComposeResult:
        """Create the 2FA interface."""
        with Container(id="twofa-dialog"):
            yield Static(
                "[bold #9d4edd]Two-Factor Authentication[/]",
                id="twofa-title",
            )

            # Build description based on available methods
            description = "Your account requires two-factor authentication.\n"

            if self.available_methods.get("TOTP") == 1:
                description += "• TOTP (Authenticator App) available\n"

            fido_keys = self.available_methods.get("FIDO2", {}).get(
                "RegisteredKeys", []
            )
            if fido_keys:
                description += f"• FIDO2/U2F ({
                    len(fido_keys)} security key(s)) available\n"
                for key in fido_keys:
                    description += f"  - {key.get('Name', 'Unknown key')}\n"

            description += "\nEnter your TOTP code to complete authentication."

            yield Static(
                description,
                id="twofa-description",
            )

            yield Static("2FA Code:", classes="twofa-label")
            yield Input(
                placeholder="Enter 6-digit code",
                id="twofa-code",
                max_length=6,
                password=True,  # Mask the input like a password
            )

            yield Static("", id="twofa-status")

            with Horizontal(id="twofa-buttons"):
                yield Button("Verify", variant="primary", id="verify-button")
                yield Button("Cancel", variant="default", id="cancel-twofa-button")

    def on_mount(self) -> None:
        """Focus the code input when modal opens."""
        self.query_one("#twofa-code", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "verify-button":
            self.action_verify()
        elif event.button.id == "cancel-twofa-button":
            self.action_cancel()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input field."""
        if event.input.id == "twofa-code":
            self.action_verify()

    def action_verify(self) -> None:
        """Verify the 2FA code."""
        code_input = self.query_one("#twofa-code", Input)
        status_widget = self.query_one("#twofa-status", Static)

        code = code_input.value.strip()

        # Validate input
        if not code:
            status_widget.update("[red]⚠ Please enter your 2FA code[/]")
            code_input.focus()
            return

        if len(code) != 6 or not code.isdigit():
            status_widget.update("[red]⚠ Code must be 6 digits[/]")
            code_input.focus()
            return

        # Return code to the app
        self.dismiss(code)

    def action_cancel(self) -> None:
        """Cancel 2FA verification."""
        self.dismiss(None)


class ToolsModal(ModalScreen[list]):
    """Modal screen for selecting which tools to enable for API requests."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    # Available tools that can be selected
    AVAILABLE_TOOLS = [
        "proton_info",
        "web_search",
        "stock",
        "weather",
        "cryptocurrency",
    ]

    def __init__(self, current_tools: list = None):
        """Initialize the tools modal.

        Args:
            current_tools: List of currently enabled tools
        """
        super().__init__()
        self.current_tools = current_tools or ["proton_info"]

    def compose(self) -> ComposeResult:
        """Create the tools selection interface."""
        with Container(id="tools-dialog"):
            yield Static(
                "[bold #9d4edd]Select Tools[/]",
                id="tools-title",
            )
            yield Static(
                "Choose which tools to enable for API requests:\n",
                id="tools-description",
            )

            # Create checkboxes for each tool
            for tool in self.AVAILABLE_TOOLS:
                is_checked = tool in self.current_tools
                yield Checkbox(
                    tool.replace("_", " ").title(),
                    value=is_checked,
                    id=f"tool-{tool}",
                )

            # yield Static(
            #     "\n[dim]At least one tool must be selected[/]",
            #     id="tools-note",
            # )

            with Horizontal(id="tools-buttons"):
                yield Button("Apply", variant="primary", id="apply-tools-button")
                yield Button("Cancel", variant="default", id="cancel-tools-button")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "apply-tools-button":
            # Collect selected tools
            selected_tools = []
            for tool in self.AVAILABLE_TOOLS:
                checkbox = self.query_one(f"#tool-{tool}", Checkbox)
                if checkbox.value:
                    selected_tools.append(tool)

            self.dismiss(selected_tools)
        elif event.button.id == "cancel-tools-button":
            self.dismiss(None)

    def action_cancel(self) -> None:
        """Cancel tool selection."""
        self.dismiss(None)


class SplashScreenModal(ModalScreen):
    """Splash screen modal that displays the purple cat image for 1.5 seconds."""

    # Add action to dismiss
    BINDINGS = [
        ("escape", "dismiss_splash", ""),
    ]

    def __init__(self, image_path: str, duration: float = 2.0):
        """Initialize splash screen.

        Args:
            image_path: Path to the image file to display
            duration: Duration in seconds to display the splash (default: 2.0)
        """
        super().__init__()
        self.image_path = image_path
        self.duration = duration

    def compose(self) -> ComposeResult:
        """Create the splash screen content."""
        with Container(id="splash-container"):
            if TEXTUAL_IMAGE_AVAILABLE and os.path.exists(self.image_path):
                try:
                    yield Static(
                        "[bold #ffd60a]Welcome to pyLumo TUI[/]", id="splash-text"
                    )

                    # Create Image widget - size controlled by CSS
                    img = Image(self.image_path, id="splash-image")
                    # Set inline styles for width and height (66% of original 80x40)
                    img.styles.width = 53
                    img.styles.height = 26
                    yield img

                    yield Static(f"\n[bold]Ver. {__version__}[/]", id="splash-version")
                except Exception:
                    # Fallback to text if image fails to load
                    yield Static(
                        "[bold #9d4edd]🐱 pyLumo TUI[/]\n\n"
                        "[bold #ffd60a]Welcome to pyLumo TUI[/]\n"
                        f"[dim #c77dff]Ver. {__version__}[/]\n\n"
                        "[dim #ffd60a]Loading...[/]",
                        id="splash-fallback",
                    )
            else:
                # Fallback if textual-image not available or image doesn't exist
                yield Static(
                    "[bold #9d4edd]🐱 pyLumo TUI[/]\n\n"
                    "[bold #ffd60a]Welcome to pyLumo TUI[/]\n"
                    f"[dim #c77dff]Ver. {__version__}[/]\n\n"
                    "[dim #ffd60a]Loading...[/]",
                    id="splash-fallback",
                )

    def on_mount(self) -> None:
        """Set timer to auto-dismiss after duration."""
        self.set_timer(self.duration, self.action_dismiss_splash)

    def action_dismiss_splash(self) -> None:
        """Action to dismiss the splash screen."""
        self.dismiss()
