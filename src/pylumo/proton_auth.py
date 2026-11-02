"""Obtain an authenticated Proton session by delegating the SRP login and the
browser-assisted CAPTCHA (human-verification) solve to the proven
Arsylk/proton-auth CLI, then map its JSON output into a pyLumo session dump
that client.load_session() accepts.

This is integration glue for an external, MIT-licensed Go tool
(github.com/Arsylk/proton-auth). It does NOT re-implement Proton's CAPTCHA:
the hard, security-sensitive human-verification proof-of-work solve stays in
the proven third-party tool, which captures the solved token by framing
Proton's captcha widget on a throwaway loopback reverse-proxy server and
intercepting the pm_captcha postMessage.

Honesty note: the JSON-to-session-dump mapping and the load_session() path are
verifiable locally, but actually running proton-auth against live Proton (real
credentials plus a live CAPTCHA challenge) cannot be validated from here.

Security notes:
- The password is passed to proton-auth via its stdin (-password-stdin), never
  in argv or the environment, so it is not visible in the process list or
  shell history.
- The session dump (which contains the AccessToken/RefreshToken/UID) is written
  to a mode-0600 temporary file, loaded, then deleted. To persist the session
  securely, call client.save_session("~/.pylumo_session.json") afterwards,
  which stores the tokens in the OS keychain.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

from .pylumo import PROTON_API_URL

__all__ = [
    "login_via_proton_auth",
    "proton_auth_session_file",
    "session_dump_from_proton_auth",
]

# Pinned proton-auth version: the Go module tag scripts/install.py builds from
# (github.com/Arsylk/proton-auth). Change it here and in scripts/install.py.
PROTON_AUTH_VERSION = "0.2.0"

# Install guidance shown when the proton-auth binary is not found.
PROTON_AUTH_INSTALL_HINT = (
    "proton-auth is not installed. It is an external, MIT-licensed Go tool "
    "(github.com/Arsylk/proton-auth) that performs Proton SRP login and "
    "transparently solves the CAPTCHA. Install one of:\n"
    "  1) python3 scripts/install.py  # builds the pinned version into ./bin\n"
    "  2) Install Go 1.26+, then run: go install "
    f"github.com/Arsylk/proton-auth/cmd/proton-auth@v{PROTON_AUTH_VERSION}"
)

# pyLumo's normal client identity (matches the vendored proton-python-client
# defaults) so a loaded session behaves like a normally-authenticated client.
_PYLUMO_APPVERSION = "Other"
_PYLUMO_USER_AGENT = "None"


def _proton_auth_binary():
    """Return the path to the proton-auth CLI, or None if it is not found.

    Search order: the $PROTON_AUTH_BIN override, the project's bin/ directory
    (walking up from this package), then the system PATH.
    """
    override = os.environ.get("PROTON_AUTH_BIN")
    if override:
        return override
    directory = os.path.dirname(os.path.abspath(__file__))
    while True:
        candidate = os.path.join(directory, "bin", "proton-auth")
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
        parent = os.path.dirname(directory)
        if parent == directory:
            break
        directory = parent
    return shutil.which("proton-auth")


def session_dump_from_proton_auth(result):
    """Map a proton-auth JSON result dict into a pyLumo session dump.

    The returned dict is a legacy-mode session dump accepted by
    ProtonSession.load(): it carries api_url, appversion, User-Agent, and a
    session_data block with UID, AccessToken, RefreshToken, Scope, PasswordMode.

    Args:
        result (dict): parsed proton-auth JSON output

    Raises:
        ValueError: if a required token key is missing from result
    """
    for key in ("accessToken", "refreshToken", "uid"):
        if key not in result:
            raise ValueError(f"proton-auth result missing required key: {key!r}")
    # proton-auth's documented JSON contract carries no scope field; the Proton
    # client models Scope as a list of strings (proton/api.py builds it with
    # auth_response["Scope"].split() and reads it with .get("Scope", [])), so an
    # empty list is the faithful mapping. Normalize a string in case a future
    # proton-auth ever emits one.
    scope = result.get("scope", [])
    if isinstance(scope, str):
        scope = scope.split()
    return {
        "api_url": PROTON_API_URL,
        "appversion": _PYLUMO_APPVERSION,
        "User-Agent": _PYLUMO_USER_AGENT,
        "session_data": {
            "UID": result["uid"],
            "AccessToken": result["accessToken"],
            "RefreshToken": result["refreshToken"],
            "Scope": scope,
            "PasswordMode": result.get("passwordMode"),
        },
    }


def proton_auth_session_file(username, password, totp=None, totp_secret=None,
                             mailbox_password=None, timeout=900):
    """Run proton-auth to log in (solving any CAPTCHA in a browser) and write a
    pyLumo session dump to a secure temporary file. Returns the file path.

    Args:
        username (str): Proton account username or email
        password (str): login password, passed to proton-auth via stdin only
        totp (str): current 2FA code, if the account has a TOTP factor
        totp_secret (str): base32 TOTP secret, if codes are generated
        mailbox_password (str): second password, for a two-password account
        timeout (int): seconds to allow for login plus the browser CAPTCHA solve

    Raises:
        RuntimeError: if proton-auth is not installed, or the login fails
    """
    binary = _proton_auth_binary()
    if binary is None:
        raise RuntimeError(PROTON_AUTH_INSTALL_HINT)
    # Transparency: show which binary is about to run with the credentials that
    # get handed to it (search order: $PROTON_AUTH_BIN, project bin/, then PATH).
    print(f"[proton-auth] binary: {binary}", file=sys.stderr)

    args = [binary, "-username", username, "-password-stdin"]
    # Keep the 2FA code/secret and the mailbox password out of argv (visible in
    # the process list): pass them to proton-auth via its PROTON_AUTH_* env only.
    env = os.environ.copy()
    if totp is not None:
        env["PROTON_AUTH_TOTP"] = totp
    if totp_secret is not None:
        env["PROTON_AUTH_TOTP_SECRET"] = totp_secret
    if mailbox_password is not None:
        env["PROTON_AUTH_MAILBOX_PASSWORD"] = mailbox_password

    # Write the proton-auth JSON result to a mode-0600 temp file (matches the
    # tool's own -o security posture); never put the password in argv or env.
    fd, out_path = tempfile.mkstemp(prefix=".proton-auth-", suffix=".json")
    os.close(fd)
    try:
        args += ["-o", out_path, "-captcha-auto-open"]
        try:
            proc = subprocess.run(
                args,
                input=(password + "\n").encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"proton-auth login timed out after {timeout}s "
                "(the browser CAPTCHA was not solved in time)"
            )
        if proc.returncode != 0:
            # On failure proton-auth writes {"error","errorCode"} to stdout and
            # leaves the -o file untouched; stderr carries the CAPTCHA hints.
            detail = (proc.stderr.decode("utf-8", "replace").strip()
                      or proc.stdout.decode("utf-8", "replace").strip())
            raise RuntimeError(
                f"proton-auth login failed (exit {proc.returncode}): {detail}"
            )
        with open(out_path, "r", encoding="utf-8") as f:
            result = json.load(f)
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass

    dump = session_dump_from_proton_auth(result)

    # Write the pyLumo session dump to a secure temp file for load_session().
    fd, dump_path = tempfile.mkstemp(prefix=".pylumo-proton-session-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(dump, f, indent=2)
    os.chmod(dump_path, 0o600)
    return dump_path


def login_via_proton_auth(client, username, password, totp=None, totp_secret=None,
                          mailbox_password=None, timeout=900):
    """Authenticate a pyLumo client by delegating login and the CAPTCHA solve to
    proton-auth, then loading the resulting session. Returns the client.

    The temporary session file is deleted after loading. To persist the session
    securely, call client.save_session("~/.pylumo_session.json") afterwards.
    """
    dump_path = proton_auth_session_file(
        username, password, totp=totp, totp_secret=totp_secret,
        mailbox_password=mailbox_password, timeout=timeout,
    )
    try:
        client.load_session(dump_path)
    finally:
        try:
            os.unlink(dump_path)
        except OSError:
            pass
    return client
