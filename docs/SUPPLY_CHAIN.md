# Supply Chain

pyLumo depends on one external binary that is not distributed on PyPI:
[`proton-auth`](https://github.com/Arsylk/proton-auth), an MIT-licensed Go
library and CLI that performs Proton SRP login and transparently solves the
CAPTCHA (human-verification) challenge. `src/pylumo/proton_auth.py` delegates
the login/CAPTCHA path to it and maps its JSON output into a session dump.

## Pinned version

| Item | Value |
| --- | --- |
| Go module | `github.com/Arsylk/proton-auth` |
| Pinned version | `0.2.0` (tag `v0.2.0`, upstream commit `7049079c767b6e26fe7b1374b28d34c2ae1bf783`) |
| Pinned in | `PROTON_AUTH_VERSION` in `src/pylumo/proton_auth.py` and `scripts/install.py` |
| Drift guard | `TestProtonAuthSupplyChain` in `tests/test_pylumo.py` fails if the two pins diverge |

Bumping the version means editing both constants; the test tells you if you
missed one.

## How the binary is obtained

`scripts/install.py` builds it **from source at the pinned tag**:

```bash
go install github.com/Arsylk/proton-auth/cmd/proton-auth@v0.2.0
```

The copy in `$(go env GOPATH)/bin` is then installed to the project's `bin/`
directory (mode `0755`, gitignored) and verified by running its own `-version`
flag; a mismatch aborts the install.

Provenance rests on the Go module proxy and its checksum database, which is
why no prebuilt binary is ever vendored in this repository. Building requires
Go 1.26+; `--skip-proton-auth` skips the step if you place the binary in
`./bin` or on `PATH` yourself.

## Verifying a local copy

```bash
bin/proton-auth -version          # must report the pinned version
go version -m bin/proton-auth     # embedded module path, version, dependency hashes
shasum -a 256 bin/proton-auth     # varies per toolchain; pin the module version
```

## Superseded: the prebuilt download (pre-November 2025)

Earlier copies of this project used a prebuilt macOS arm64 asset downloaded
from the upstream releases page. That artifact was **adhoc-signed by the
linker** (`codesign -dv` reports `Signature=adhoc`, identifier `a.out`) with no
Developer ID and no notarization, so Gatekeeper gave no vendor assurance and
the file's only identity was its hash:

```
493b71953a8cfd21303c310fcf4741d3c7127b009f9ecda652712da97f758745
```

A source build is **also** adhoc-signed by the Go linker, so `codesign` does not
tell the two artifacts apart. Discriminate by contract and provenance instead:
`bin/proton-auth -version` must report the pinned version, and
`go version -m bin/proton-auth` must show `mod github.com/Arsylk/proton-auth` at
that version. A copy failing either is stale or foreign: replace it by running
`python3 scripts/install.py`. A source build's file hash also varies with the Go
toolchain and build path, which is why the pin is the module version, not a hash.

## Runtime resolution

`_proton_auth_binary()` resolves the CLI in this order:

1. `$PROTON_AUTH_BIN` (explicit override — a deliberate escape hatch for
   development builds; nothing validates it for you)
2. the project's `bin/proton-auth`, walking up from the installed package
3. `PATH`

The resolved path is printed to stderr before the tool runs, so you can see
which binary is about to receive your credentials. The password is passed to it
over stdin only and the 2FA code, TOTP secret and mailbox password over
`PROTON_AUTH_*` environment variables only, never in `argv`, where they would
be visible in the process list.
