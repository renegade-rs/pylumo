"""
pylumo - A Python client and TUI for the Lumo Proton API with hybrid encryption.
"""

__version__ = "0.0.1"

from pylumo.pylumo import (
    pyLumo,
    LumoTools,
    LumoModel,
    Role,
    ResponseMessageType,
    ContextLimits,
    estimate_token_count,
    get_context_warning_level,
    LUMO_BASE_URL,
    LUMO_API_URL,
)

from .proton_auth import (
    login_via_proton_auth,
    proton_auth_session_file,
    session_dump_from_proton_auth,
)

__all__ = [
    "__version__",
    "pyLumo",
    "LumoTools",
    "LumoModel",
    "Role",
    "ResponseMessageType",
    "ContextLimits",
    "estimate_token_count",
    "get_context_warning_level",
    "LUMO_BASE_URL",
    "LUMO_API_URL",
    "login_via_proton_auth",
    "proton_auth_session_file",
    "session_dump_from_proton_auth",
]
