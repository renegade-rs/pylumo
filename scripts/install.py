#!/usr/bin/env python3
"""
pylumo Installation Script

This is the recommended way to install pylumo. It automatically handles
the proton-client dependency which has build issues on some systems.

Usage:
    python3 install.py           # Install CLI only
    python3 install.py --tui     # Install with TUI support (recommended)
    python3 install.py --dev     # Install with development tools
    python3 install.py --all     # Install everything

What it does:
    1. Builds the pinned proton-auth login/CAPTCHA solver from source
    2. Clones and patches proton-client to fix build errors
    3. Installs the patched proton-client
    4. Installs pylumo with your chosen extras

For more information, see INSTALL.md and KNOWN_ISSUES.md
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
import os
import re

# Pinned proton-auth version: the Go module tag built by install_proton_auth().
# Keep in sync with PROTON_AUTH_VERSION in src/pylumo/proton_auth.py.
PROTON_AUTH_VERSION = "0.2.0"

def _uv_subprocess_env():
    env = os.environ.copy()
    env["PYENV_VERSION"] = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    env["UV_PYTHON"] = sys.executable
    return env

def _get_site_packages_dir() -> str:
    """Get the site-packages directory for the current Python."""
    import sysconfig
    return sysconfig.get_path('purelib')


def _patch_proton_srp_for_macos() -> None:
    """Patch proton's srp/__init__.py to skip _ctsrp on macOS.
    
    On macOS with hardened runtime, loading libssl.dylib via ctypes causes
    a SIGABRT. This patch forces the pure Python SRP implementation.
    """
    if sys.platform != 'darwin':
        return
    
    site_packages = _get_site_packages_dir()
    srp_init_path = os.path.join(site_packages, 'proton', 'srp', '__init__.py')
    
    if not os.path.exists(srp_init_path):
        print(f"  Warning: Could not find {srp_init_path} to patch")
        return
    
    with open(srp_init_path, 'r') as f:
        content = f.read()
    
    # Check if already patched
    if 'PATCHED FOR MACOS' in content:
        return
    
    # Replace the __init__.py to skip _ctsrp entirely on macOS
    patched_content = '''# PATCHED FOR MACOS: Skip _ctsrp to avoid libssl.dylib SIGABRT
# The ctypes-based _ctsrp module crashes on macOS with hardened runtime
# when it tries to load libssl.dylib. Use pure Python _pysrp instead.
import sys

from . import _pysrp
_mod = _pysrp

# Only try _ctsrp on non-Darwin platforms
if sys.platform != 'darwin':
    try:
        from . import _ctsrp
        _mod = _ctsrp
    except (ImportError, OSError):
        pass

User = _mod.User
'''
    
    with open(srp_init_path, 'w') as f:
        f.write(patched_content)


def _patch_proton_cert_pinning_for_urllib3() -> None:
    """Patch proton's cert_pinning.py for urllib3 2.x compatibility.

    urllib3 2.0 removed `strict` from HTTPSConnectionPool.__init__. The fork
    subclasses it and calls the parent positionally, so under urllib3 2.x every
    later argument shifts by one, landing `strict` in the parent `timeout` slot
    (Timeout.from_float -> ValueError), which breaks Proton API auth at runtime.
    Rewrite the call to pass by keyword and include `strict` only when the
    parent signature accepts it (checked via inspect.signature).
    """
    site_packages = _get_site_packages_dir()
    pin_path = os.path.join(site_packages, "proton", "cert_pinning.py")
    if not os.path.exists(pin_path):
        print(f"  Warning: Could not find {pin_path} to patch")
        return
    with open(pin_path, "r") as f:
        content = f.read()
    # Check if already patched
    if "PATCHED FOR URLLIB3 v2" in content:
        return
    pattern = re.compile(
        r"(self\.hash_dict = hash_dict[ \t]*\n)([ \t]*)#.*?except TypeError:.*?\n[ \t]*\)[ \t]*\n",
        re.DOTALL,
    )
    replacement = (
        r"\1\2# PATCHED FOR URLLIB3 v2: urllib3 2.0 removed `strict` from\n"
        r"\2# HTTPSConnectionPool.__init__. The positional super() call then shifts\n"
        r"\2# every later arg by one, landing `strict` in the parent `timeout` slot\n"
        r"\2# (Timeout.from_float -> ValueError), breaking Proton auth on 2.x.\n"
        r"\2# Pass by keyword; include `strict` only when the parent accepts it.\n"
        r"\2_kw = dict(\n"
        r"\2    host=host, port=port, timeout=timeout, maxsize=maxsize,\n"
        r"\2    block=block, headers=headers, retries=retries,\n"
        r"\2    _proxy=_proxy, _proxy_headers=_proxy_headers,\n"
        r"\2    key_file=key_file, cert_file=cert_file, cert_reqs=cert_reqs,\n"
        r"\2    key_password=key_password, ca_certs=ca_certs,\n"
        r"\2    ssl_version=ssl_version, assert_hostname=assert_hostname,\n"
        r"\2    assert_fingerprint=assert_fingerprint, ca_cert_dir=ca_cert_dir,\n"
        r"\2    **conn_kw,\n"
        r"\2)\n"
        r'\2if "strict" in inspect.signature(HTTPSConnectionPool.__init__).parameters:\n'
        r'\2    _kw["strict"] = strict\n'
        r"\2super(TLSPinningHTTPSConnectionPool, self).__init__(**_kw)\n"
    )
    new_content, n = pattern.subn(replacement, content, count=1)
    if n == 0:
        print(f"  Warning: TLS-pinning pattern not found in {pin_path}; skipping")
        return
    # Insert `import inspect` (needed by the patched call) after `import base64`
    if not re.search(r"^import inspect$", new_content, re.MULTILINE):
        new_content = new_content.replace("import base64\n", "import base64\nimport inspect\n", 1)
    with open(pin_path, "w") as f:
        f.write(new_content)


# Version declared by the pinned proton-python-client source
# (https://github.com/WugtheFlunk/proton-python-client main @ e03e626).
PROTON_CLIENT_VERSION = "0.7.1"


def install_proton_client(proton_ref: str, expected_commit: str | None) -> None:
    """Install proton-client with patched setup.py to avoid build errors"""
    print("=" * 60)
    print("Installing proton-client (with build workaround)...")
    print("=" * 60)
    
    # First install setuptools and wheel
    print("\n[0/4] Installing build dependencies...")
    result = subprocess.run([
        "uv", "pip", "install", "--python", sys.executable, "setuptools", "wheel"
    ], capture_output=True, text=True, env=_uv_subprocess_env())
    
    if result.returncode != 0:
        print(f"Error installing build dependencies: {result.stderr}")
        sys.exit(1)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        print("\n[1/4] Cloning proton-python-client repository...")
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                proton_ref,
                "https://github.com/WugtheFlunk/proton-python-client", #"https://github.com/ProtonMail/proton-python-client",
                temp_dir,
            ],
            check=True,
            capture_output=True,
        )

        commit_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        installed_commit = commit_result.stdout.strip()
        print(f"[1/4] Pinned ref: {proton_ref}")
        print(f"[1/4] Installed commit: {installed_commit}")
        if expected_commit is not None and installed_commit != expected_commit:
            print(
                "Error: proton-python-client commit mismatch. "
                f"Expected {expected_commit} but got {installed_commit}."
            )
            sys.exit(1)
        
        setup_py_path = os.path.join(temp_dir, "setup.py")
        
        print("[2/4] Patching setup.py to fix build issue...")
        with open(setup_py_path, 'r') as f:
            content = f.read()
        
        # Replace the problematic import that causes SIGABRT
        content = content.replace(
            'from proton.constants import VERSION',
            f'VERSION = "{PROTON_CLIENT_VERSION}"'
        )
        
        with open(setup_py_path, 'w') as f:
            f.write(content)
        
        print("[3/4] Installing proton-client...")
        result = subprocess.run([
            "uv", "pip", "install", "--python", sys.executable, temp_dir
        ], capture_output=True, text=True, env=_uv_subprocess_env())
        
        if result.returncode != 0:
            print(f"Error installing proton-client: {result.stderr}")
            sys.exit(1)
        
        # Patch the installed srp module for macOS
        if sys.platform == 'darwin':
            print("[4/4] Patching proton SRP for macOS compatibility...")
            _patch_proton_srp_for_macos()

        # Patch the installed TLS-pinning module for urllib3 2.x compatibility
        print("[4/4] Patching proton TLS pinning for urllib3 compatibility...")
        _patch_proton_cert_pinning_for_urllib3()
        
        print("[4/4] ✓ proton-client installed successfully\n")

def install_proton_auth(version: str) -> None:
    """Build the pinned proton-auth CLI from source into ./bin.

    Provenance comes from the Go module proxy and its checksum database, so no
    prebuilt binary blob is ever vendored. The built CLI is copied into the
    project's bin/ directory (which the proton_auth adapter searches before
    PATH) and verified by running its own -version flag.
    """
    print("=" * 60)
    print("Installing proton-auth (login/CAPTCHA solver)...")
    print("=" * 60)

    go = shutil.which("go")
    if go is None:
        print(f"Error: Go 1.26+ is required to build proton-auth v{version}.")
        print("To install it:")
        print("  brew install go")
        print("Then re-run this script, or pass --skip-proton-auth to place")
        print("the binary yourself.")
        sys.exit(1)

    print(f"\n[1/3] Building proton-auth@v{version} from source...")
    result = subprocess.run(
        [go, "install", f"github.com/Arsylk/proton-auth/cmd/proton-auth@v{version}"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"Error building proton-auth: {result.stderr}")
        sys.exit(1)

    print("[2/3] Installing the built binary into ./bin...")
    gopath = subprocess.run([go, "env", "GOPATH"], capture_output=True, text=True)
    go_bin = os.path.join(
        gopath.stdout.strip() or os.path.expanduser("~/go"), "bin",
        "proton-auth.exe" if os.name == "nt" else "proton-auth",
    )
    if not os.path.isfile(go_bin):
        print(f"Error: built binary not found at {go_bin}")
        sys.exit(1)
    bin_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
    os.makedirs(bin_dir, exist_ok=True)
    dest = os.path.join(bin_dir, os.path.basename(go_bin))
    shutil.copyfile(go_bin, dest)
    os.chmod(dest, 0o755)

    print(f"[3/3] Verifying the binary reports v{version}...")
    result = subprocess.run([dest, "-version"], capture_output=True, text=True)
    if result.returncode != 0 or version not in f"{result.stdout}{result.stderr}":
        print(f"Error: proton-auth -version did not report v{version}:")
        print(result.stdout or result.stderr)
        sys.exit(1)
    print("✓ proton-auth installed and version-verified\n")


def install_pylumo(extras=None):
    """Install pylumo with optional extras"""
    print("=" * 60)
    print("Installing pylumo...")
    print("=" * 60)
    
    cmd = ["uv", "pip", "install", "--python", sys.executable, "-e", "."]
    
    if extras:
        extras_str = ",".join(extras)
        cmd[-1] = f".[{extras_str}]"
        print(f"\nInstalling with extras: {extras_str}")
    
    result = subprocess.run(cmd, capture_output=True, text=True, env=_uv_subprocess_env())
    
    if result.returncode != 0:
        print(f"Error installing pylumo: {result.stderr}")
        sys.exit(1)
    
    print("✓ pylumo installed successfully\n")

def check_system_dependencies():
    """Check if required system dependencies are installed"""
    import shutil
    
    # Check for GnuPG
    if not shutil.which("gpg"):
        print("⚠️  WARNING: GnuPG (gpg) not found!")
        print("")
        print("GnuPG is required for Proton authentication.")
        print("To install it:")
        print("  brew install gnupg")
        print("")
        print("You can continue without it, but Proton login will not work.")
        print("")
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            print("Installation cancelled.")
            sys.exit(1)
        print("")

def main():
    parser = argparse.ArgumentParser(
        description="Install pylumo with proper handling of proton-client dependency"
    )
    parser.add_argument("--tui", action="store_true", help="Install with TUI support")
    parser.add_argument("--dev", action="store_true", help="Install with development tools")
    parser.add_argument("--all", action="store_true", help="Install with all optional dependencies")
    parser.add_argument(
        "--proton-client-ref",
        default="main",
        help="Pinned proton-python-client git ref (tag/branch) to install (default: main)",
    )
    parser.add_argument(
        "--proton-client-commit",
        default="e03e62688a70f0f35c725fc89cc5f14e1652b239",
        help="Expected proton-python-client commit SHA to verify after clone (default: e03e626 on fork main)",
    )
    parser.add_argument(
        "--proton-auth-version",
        default=PROTON_AUTH_VERSION,
        help="Pinned proton-auth Go module version to build from source",
    )
    parser.add_argument(
        "--skip-proton-auth",
        action="store_true",
        help="Skip building proton-auth (place the binary in ./bin or on PATH yourself)",
    )
    
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("pylumo Installation Script")
    print("=" * 60 + "\n")
    
    # Check system dependencies
    check_system_dependencies()
    
    # Determine which extras to install
    extras = []
    if args.all:
        extras = ["all"]
    else:
        if args.tui:
            extras.append("tui")
        if args.dev:
            extras.append("dev")
    
    # Step 1: Build the pinned proton-auth login/CAPTCHA solver
    if args.skip_proton_auth:
        print("Skipping proton-auth build (--skip-proton-auth).")
    else:
        install_proton_auth(args.proton_auth_version)

    # Step 2: Install proton-client with workaround
    install_proton_client(args.proton_client_ref, args.proton_client_commit)

    # Step 3: Install pylumo
    install_pylumo(extras if extras else None)
    
    print("=" * 60)
    print("Installation Complete!")
    print("=" * 60)
    print("\nYou can now run pylumo using one of the following options:")
    print("\nOption A (recommended): uv run")
    print("  uv run pylumo --help     # CLI interface")
    if args.tui or args.all:
        print("  uv run pylumo-tui        # Terminal UI")

    print("\nOption B: project venv")
    print("  ./.venv/bin/pylumo --help")
    if args.tui or args.all:
        print("  ./.venv/bin/pylumo-tui")

    print("\nOption C: activate the venv")
    print("  source .venv/bin/activate")
    print("  pylumo --help")
    if args.tui or args.all:
        print("  pylumo-tui")
    print("\n")

if __name__ == "__main__":
    main()
