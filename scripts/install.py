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
    1. Clones and patches proton-client to fix build errors
    2. Installs the patched proton-client
    3. Installs pylumo with your chosen extras

For more information, see INSTALL.md and KNOWN_ISSUES.md
"""
import argparse
import subprocess
import sys
import tempfile
import os

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
                #"--branch",
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
            f'VERSION = "{proton_ref}"'
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
        
        print("[4/4] ✓ proton-client installed successfully\n")

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
        default="0.7.1",
        help="Pinned proton-python-client git ref (tag/branch) to install (default: 0.7.1)",
    )
    parser.add_argument(
        "--proton-client-commit",
        default=None,
        help="Optional expected proton-python-client commit SHA to verify after clone",
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
    
    # Step 1: Install proton-client with workaround
    install_proton_client(args.proton_client_ref, args.proton_client_commit)
    
    # Step 2: Install pylumo
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
