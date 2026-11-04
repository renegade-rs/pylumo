# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [0.1.0] - 2026-11-04
### Added
- API monitor page (`GET /` and `GET /monitor.js`, served without auth) modeled on
  the Strata monitor: per-request token usage and timings (time to first token,
  wall-clock, decode tokens/s, prefill tokens/s), the served model catalog (highlighting the active model), and live
  CPU/memory and GPU usage.
- Authenticated monitor data endpoints `GET /api/requests` and `GET /api/status`
  (Bearer key), backed by a thread-safe bounded request-metrics deque so the last
  100 requests survive a server restart.
- System sampler thread updates CPU busy and memory percent via `psutil` every
  2 seconds and reads GPU utilization from a small JSON file written by a
  privileged `powermetrics` sampler; a missing or stale file renders as a dash.
- Docker support: multi-stage `Dockerfile` (uv-reproducible, non-root) serving
  the monitor and API on `0.0.0.0:8443` with a health check, and
  `docker-compose.yaml` injecting the host-side `.env` at runtime (secrets
  never baked into the image) bind-mounting the host's `~/.local/share/pylumo`
  so the persisted API key, logs and GPU sampler file are shared with a
  native install; the monitor's GPU tile shows host utilization on Docker
  Desktop.

### Changed
- Secure application directory on macOS moved to `~/.local/share/pylumo`
  (same as Linux); existing persisted state relocates once.

### Fixed
- Declare `psutil` (used by the system sampler) in the project dependencies so
  fresh installs get live CPU/memory tiles; it previously worked only where
  psutil had been installed out-of-band.

## [0.0.1] - 2026-01-06
### Added
- Initial release.