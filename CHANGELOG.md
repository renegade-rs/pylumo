# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]
### Added
- API monitor page (`GET /` and `GET /monitor.js`, served without auth) modeled on
  the Strata monitor: per-request token usage and timings (time to first token,
  wall-clock, decode tokens/s, prefill tokens/s), live CPU/memory, and GPU usage.
- Authenticated monitor data endpoints `GET /api/requests` and `GET /api/status`
  (Bearer key), backed by a thread-safe bounded request-metrics deque so the last
  100 requests survive a server restart.
- System sampler thread updates CPU busy and memory percent via `psutil` every
  2 seconds and reads GPU utilization from a small JSON file written by a
  privileged `powermetrics` sampler; a missing or stale file renders as a dash.

## [0.0.1] - 2026-01-06
### Added
- Initial release.