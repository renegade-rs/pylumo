# pylumo

> **Fork notice:** this repository is a fork of
> [Mindgard/pylumo](https://github.com/Mindgard/pylumo) by
> [Mindgard](https://mindgard.ai), maintained by renegade-rs
> <rs@rhodium.dscloud.me>. Original authorship and the upstream project
> remain credited to Mindgard; the project is licensed under
> GPL-3.0-or-later.

<p align="center">
  <img src="src/pylumo/_purp_cat.png" alt="pyLumo" width="400">
</p>

A Python client and terminal UI for the [Proton Lumo](https://lumo.proton.me) AI assistant with end-to-end encryption. A blogpost about the pyLumo project can be found [here](https://mindgard.ai/blog/understanding-lumo-ai-assistant-announcing-pylumo).

## Table of Contents

- [Features](#features)
- [Installation](#installation)
  - [Quick Install (Recommended)](#quick-install-recommended)
  - [Using uv](#using-uv)
- [Quick Start](#quick-start)
  - [Terminal UI](#terminal-ui)
  - [Command Line](#command-line)
  - [Local API Server](#local-api-server)
- [Python API](#python-api)
- [Testing](#testing)
- [Uninstall](#uninstall)
- [Security](#security)
- [License](#license)
- [Links](#links)

## Features

- **End-to-end encryption** using AES-256-GCM + PGP hybrid encryption
- **Terminal UI (TUI)** with rich markdown rendering and inline images
- **CLI interface** for scripting and automation
- **Proton authentication** with secure session storage in system keychain
- **Guest mode** for unauthenticated access
- **Tool support**: web search, weather, stocks, cryptocurrency
- **Local API server** exposing Lumo via the OpenAI chat completions API

## Installation

**Requirements:** Python 3.12+, GnuPG, and the `proton-auth` binary
(0.2.0, from [Arsylk/proton-auth](https://github.com/Arsylk/proton-auth))
for login/CAPTCHA delegation

### Quick Install (Recommended)

Clone the repository and use the Makefile:

```bash
git clone git@github.com:renegade-rs/pylumo.git
cd pylumo

# Install with TUI support (recommended)
make install-tui

# Or CLI only
make install
```

The installer automatically handles all dependencies including the Proton Python client.

Note: Proton account authentication depends on Proton's `proton-python-client`. It is intentionally installed via `scripts/install.py` (rather than as a normal python dependency) due to upstream build issues. The installer pins a specific git ref and prints the exact commit hash that was installed (currently `0.7.1`, `main` at `e03e626`, from the backup repository).

### Using uv

If you prefer to use [uv](https://github.com/astral-sh/uv) directly:

```bash
# Create virtual environment
uv venv --python 3.12
source .venv/bin/activate

# Install (recommended): installs pylumo and a patched proton-python-client
# required for Proton authentication. The installer prints the pinned ref and
# installed commit hash.
python3 scripts/install.py --tui
```

## Quick Start

### Terminal UI

<p align="center">
  <img src="docs/pylumo_tui_screenshot.png" alt="pyLumo TUI">
</p>

```bash
# run via uv
uv run pylumo-tui

# or run from the project venv created by `make install-*`
./.venv/bin/pylumo-tui

# r activate the venv and run normally
source .venv/bin/activate
pylumo-tui
```

**Keyboard shortcuts:**
| Key | Action |
|-----|--------|
| `^L` | Login to Proton |
| `^K` | Logout |
| `^S` | Save chat |
| `^U` | Upload file |
| `^X` | Clear chat |
| `F1` | About |
| `F2` | Toggle debug panel |
| `F10` | Save debug output |
| `^\` | Command palette |
| `^Q` | Quit |

### Command Line

```bash
# Simple query (guest mode)
uv run pylumo "What is the capital of France?"

# With file upload
uv run pylumo -u document.pdf "Summarize this document"

# Pipe input
echo "Explain quantum computing" | uv run pylumo

# Save output to file
uv run pylumo -o response.txt "Write a haiku about coding"

# Use tools (e.g., cryptocurrency prices)
uv run pylumo "What is the current price of POPCAT?" --tools cryptocurrency
```

If you've activated the venv (`source .venv/bin/activate`), you can also run
`pylumo` and `pylumo-tui` directly without `uv run`.

**CLI Options:**
```
pylumo [PROMPT] [OPTIONS]

Arguments:
  PROMPT                  The prompt to send (before options, or via stdin)

Options:
  --tools TOOL [TOOL ...] Enable tools: proton_info, web_search, weather, stock, cryptocurrency
  --targets TARGET [...]  Response targets (default: title, message)
  -q, --quiet             Quiet mode (raw output only)
  -d, --debug             Debug mode (HTTP debugging)
  -o, --output FILE       Save output to file
  -u, --upload FILE       Upload a file with the request
```

### Local API Server

Starts a loopback HTTP server that exposes Lumo through the OpenAI chat
completions API, compatible with any tool that speaks the OpenAI protocol
(opencode, GitHub Copilot BYOK, Cursor, Continue, aider). Adapted from the
`proton lumo serve` design in
[major0/proton-utils](https://github.com/major0/proton-utils): same API key
format (32 random bytes, hex-encoded), same endpoints, and the same startup
banner posture (the key is printed once to stderr and persisted with mode
0600).

```bash
# Start the server (guest mode unless a saved session is found)
uv run pylumo-serve

# Generate and persist a new API key, listen on a custom address
uv run pylumo-serve --new-api-key --addr 127.0.0.1:8443

# Enable Lumo's web_search tool by default
uv run pylumo-serve --web-search
```

The API key is never accepted via argv (it stays out of the process list);
it is read from the `LUMO_API_KEY` environment variable or the persisted key
file. If neither exists, a new 64-char hex key is generated, persisted with
mode 0600, and printed once to stderr at startup.

**Server Options:**
```
pylumo-serve [OPTIONS]

Options:
  --addr ADDR           Listen address and port (default: 127.0.0.1:8443;
                        overridable via env LUMO_ENDPOINT)
  --new-api-key         Generate and persist a new API key
  --tls-cert TLS_CERT   TLS certificate path
  --tls-key TLS_KEY     TLS private key path
  --web-search          Enable Lumo's web_search tool by default
                        (overridable via env LUMO_WEB_SEARCH)
```

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/chat/completions` | Chat completions (streaming SSE) |
| GET | `/v1/models` | List available models |
| GET | `/` | Monitor page (no auth) |
| GET | `/monitor.js` | Monitor page script (no auth) |
| GET | `/api/requests` | Recent request records (Bearer key) |
| GET | `/api/status` | Model, in-flight, and system metrics (Bearer key) |

**Reasoning Modes:**

Lumo offers two reasoning modes, not a graded scale. **Fast** answers as
quickly as possible; **Thinking** works through a request step by step before
answering. The server picks between them with the OpenAI `reasoning_effort`
field, where any level other than `none` means Thinking, so `low`, `medium`
and `high` are equivalent. A request that names neither gets Fast, matching
the posture Lumo's own clients default to.

| Request | Mode | Sent to Lumo |
|---------|------|--------------|
| `"reasoning_effort": "low"` / `"medium"` / `"high"` | Thinking | `"high"` |
| `{"thinking": {"type": "enabled"}}` | Thinking | `"high"` |
| `"reasoning_effort": "none"` | Fast | `"none"` |
| field absent | Fast | `"none"` |

Thinking output is surfaced as `message.reasoning_content` (non-streaming) and
`delta.reasoning_content` (streaming SSE).

**Model and mode matrix** (from
[Proton's guide to Lumo models and modes](https://proton.me/support/lumo-models)):

| Task | Model | Mode |
|------|-------|------|
| Quick questions and lookups | `lumo-lite` | Fast |
| General writing or editing | `lumo-lite` | Thinking |
| Brainstorming and ideation | `lumo-max` | Fast |
| Coding and technical tasks | `lumo-max` | Thinking |
| Unsure | `lumo-max` | Fast |

`apertus-15` is the fully open Swiss model. Its
[technical report](https://huggingface.co/papers/2610.15542) describes thinking
as a flag in the chat template rather than a separate model, so one set of
weights serves both modes. Live requests confirm the two families differ in
where the reasoning lands: Lumo Max and Lite return it as a separate channel,
which the server surfaces as `reasoning_content`, while Apertus writes its
chain of thought inline in `message.content`, so `reasoning_content` stays
empty for that model.

**Harness config** (opencode / GitHub Copilot BYOK / Cursor), same shape as
proton-utils' docs:

```json
{"models": [{"title": "Lumo Max", "model": "lumo-max", "provider": "openai"}],
 "openai": {"baseUrl": "http://127.0.0.1:8443/v1", "apiKey": "<your-api-key>"}}
```

For OpenCode, add the server as an OpenAI-compatible provider and declare
reasoning support so variants are offered:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "model": "lumo/apertus-15",
  "providers": {
    "lumo": {
      "name": "Lumo",
      "package": "@opencode/ai/providers/openai-compatible",
      "settings": {
        "baseURL": "http://127.0.0.1:8443/v1",
        "apiKey": "{env:LUMO_API_KEY}"
      },
      "models": {
        "apertus-15": {
          "modelID": "apertus-15",
          "capabilities": {
            "tools": true,
            "input": ["text"],
            "output": ["text"],
            "reasoning": { "supported": true, "toggle": true, "effort": ["low", "high"] }
          },
          "compatibility": { "reasoningField": "reasoning_content" }
        }
      }
    }
  }
}
```

Select a mode with `lumo/apertus-15#high` (Thinking) or `lumo/apertus-15#none`
(Fast). Because Lumo's thinking is binary, `#low` and `#high` behave the same.

### Run in the background, stop, and monitor

**Foreground.** The commands above run the server in the terminal. Stop it with
`Ctrl-C` (SIGINT) or `kill <pid>` (SIGTERM).

**Background service (launchd).** To start the server at login and restart it
automatically, register it as a LaunchAgent whose `ProgramArguments` run your
virtualenv's `pylumo-serve` (for example `.venv/bin/pylumo-serve --web-search`),
with `RunAtLoad` and `KeepAlive` set to true. The server reads its API key from
the persisted key file, so the key is never stored in the property list.

```bash
# Start (bootstrap) the server agent for the current GUI session
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/dev.renegade.pylumo.serve.plist
# Stop (bootout) it
launchctl bootout "gui/$(id -u)/dev.renegade.pylumo.serve"
```

GPU utilization is collected by a separate privileged sampler that runs
`powermetrics` as a LaunchDaemon and writes a small JSON file the server reads.
Because it runs as root, installing and removing it need `sudo`:

```bash
# Start the GPU sampler daemon
sudo launchctl bootstrap system /Library/LaunchDaemons/dev.renegade.pylumo.gpu.plist
# Stop it
sudo launchctl bootout system/dev.renegade.pylumo.gpu
```

Without the sampler the monitor's GPU tile shows a dash; CPU and memory usage
are always available.

**Monitor page.** Open [http://127.0.0.1:8443/](http://127.0.0.1:8443/) (or the
address set with `--addr`). The page itself is served without authentication; it
asks you to paste the server API key once and keeps it in browser
`sessionStorage`, then polls the authenticated `/api/requests` and `/api/status`
endpoints for per-request token usage and timings (time to first token,
wall-clock, decode tokens/s, prefill tokens/s) and live CPU, memory, and GPU
usage.

## Python API

```python
from pylumo import pyLumo, LumoTools, LumoModel, login_via_proton_auth
from dotenv import find_dotenv, load_dotenv
import os

## Guest mode (no authentication)
client = pyLumo()
response = client.send_request("Hello, Lumo!")
print(response["message"])

## Authenticated mode
## Load environment variables from .env file
load_dotenv(find_dotenv(usecwd=True)) # Search upward from kernel CWD for the repo-root .env
PROTON_USER_NAME = os.environ["PROTON_USER_NAME"] # can be username or user's email address
PROTON_PW = os.environ["PROTON_PW"]
PROTON_MAILBOX_PW = os.environ["PROTON_MAILBOX_PW"]

client = pyLumo()
login_via_proton_auth(client=client, 
                      username=os.environ["PROTON_USER_NAME"],   
                      password=PROTON_PW, 
                      mailbox_password=PROTON_MAILBOX_PW) 
client.save_session("~/.pylumo_session.json")

# With tools enabled
response = client.send_request(
    "What's the weather in Auckland?",
    tools=[LumoTools.WEATHER, LumoTools.WEB_SEARCH],
    model=LumoModel.LUMO_LITE
)
```

## Testing

```bash
# Install development dependencies (includes pytest + pytest-cov)
uv pip install -e ".[dev]"

# Run tests
uv run pytest tests/

# Run tests with coverage
uv run pytest tests/ --cov=pylumo
```

See [docs/TESTING.md](docs/TESTING.md) for more.

## Uninstall

```bash
make uninstall
```

This removes `pylumo` and the Proton client dependency from the active Python
environment used by the uninstall script.

If you installed into the project venv (`./.venv`), you can also remove it
entirely with:

```bash
rm -rf .venv
```

## Security

- Session tokens are stored in system keychain (macOS Keychain, Linux Secret Service, Windows Credential Locker)
- TLS certificate pinning enabled by default (see note below)
- All communication encrypted with AES-256-GCM
- No sensitive data written to plain files
- The login/CAPTCHA solver is built from source at a pinned version (see [docs/SUPPLY_CHAIN.md](docs/SUPPLY_CHAIN.md))

### Message integrity failures

- Streaming responses are authenticated with AES-GCM.
- If integrity verification fails (e.g., invalid tag/ciphertext), pylumo treats this as an integrity error: it stops processing further chunks and returns an explicit error.

### Local data storage

- App-owned directories are created with owner-only permissions (`0700`).
- On-disk state files (e.g., config/session pointer files) are written atomically and forced to `0600` where supported.
- Proton session tokens are stored in the OS keychain; the on-disk session file is a non-secret pointer.

### What “end-to-end encryption” means here

- Prompts and conversation turns are encrypted client-side with AES-256-GCM using a fresh per-request key.
- The per-request AES key is encrypted to Proton/Lumo’s published PGP public key and sent alongside the request.
- This protects prompt/response content against passive network observers and intermediaries; it does not protect against a compromised endpoint (your machine) or against the service itself once it decrypts.

**Note:** The [proton-python-client](https://github.com/WugtheFlunk/proton-python-client) module (a backup of the now-404 ProtonMail original at v0.7.1 [proton-python-client](https://github.com/ProtonMail/proton-python-client)) that pylumo uses to authenticate to Proton's API only includes TLS pins for VPN endpoints. pylumo [patches in the required pins](https://github.com/Mindgard/pylumo/blob/main/src/pylumo/pylumo.py#L33-L48) for `account.proton.me` at runtime to enable authentication with TLS pinning.

## License

GPL-3.0-or-later

## Links

- [Supply Chain - Pinned external builds](docs/SUPPLY_CHAIN.md)
- [Blogpost - Understanding Lumo AI Assistant: Announcing pyLumo](http://mindgard.ai/blog/understanding-lumo-ai-assistant-announcing-pylumo)
- [Proton Lumo](https://lumo.proton.me)
- [GitHub Repository](https://github.com/renegade-rs/pylumo) (this fork)
- [Mindgard](https://mindgard.ai) (upstream of this fork)
- [Arsylk/proton-auth](https://github.com/Arsylk/proton-auth) (external login/CAPTCHA solver, v0.2.0)
