#!/usr/bin/env python3
"""In-process request metrics for the pyLumo local server.

Records every authenticated chat completion with token usage and
timings, kept in a bounded deque so the last 100 requests survive
until the server restarts. Speeds follow the llama.cpp monitor
convention: decode tokens/s excludes time to first token, and
prefill tokens/s is only measurable on streaming requests.
"""
import threading
import time
from collections import deque

MAX_RECORDS = 100

STATE_ACTIVE = "active"
STATE_COMPLETED = "completed"
STATE_ERROR = "error"


class RequestRecord:
    """One chat completion request, from accepted body to final chunk."""

    __slots__ = (
        "id",
        "model",
        "path",
        "state",
        "started_at",
        "first_token_at",
        "completed_at",
        "prompt_tokens",
        "completion_tokens",
    )

    def __init__(self, model: str, path: str) -> None:
        self.id = ""
        self.model = model
        self.path = path
        self.state = STATE_ACTIVE
        self.started_at = time.time()
        self.first_token_at = None
        self.completed_at = None
        self.prompt_tokens = None
        self.completion_tokens = None

    def to_json(self) -> dict:
        """Return the monitor-facing view of this request.

        Returns:
            Dict with id, model, path, state, usage, and timings
        """
        wall = ttft = None
        if self.completed_at is not None:
            wall = self.completed_at - self.started_at
        if self.first_token_at is not None:
            ttft = self.first_token_at - self.started_at
        decode = prefill = None
        if (
            self.completion_tokens
            and wall is not None
            and ttft is not None
            and wall > ttft
        ):
            decode = self.completion_tokens / (wall - ttft)
        if self.prompt_tokens and ttft:
            prefill = self.prompt_tokens / ttft
        return {
            "id": self.id,
            "model": self.model,
            "path": self.path,
            "state": self.state,
            "started_at": int(self.started_at * 1000),
            "usage": {
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
            },
            "timings": {
                "ttft_s": ttft,
                "wall_s": wall,
                "decode_tokens_s": decode,
                "prefill_tokens_s": prefill,
            },
        }


class Metrics:
    """Thread-safe bounded store of recent request records."""

    def __init__(self, maxlen: int = MAX_RECORDS) -> None:
        self.records: deque = deque(maxlen=maxlen)
        self.lock = threading.Lock()

    def begin(self, model: str, path: str) -> RequestRecord:
        """Start recording a request that passed auth and parsing."""
        record = RequestRecord(model, path)
        with self.lock:
            self.records.append(record)
        return record

    def snapshot(self) -> list:
        """Return monitor views, newest first."""
        with self.lock:
            return [record.to_json() for record in reversed(self.records)]

    def last_finished(self) -> dict | None:
        """Return the view of the newest non-active request, or None."""
        with self.lock:
            for record in reversed(self.records):
                if record.state != STATE_ACTIVE:
                    return record.to_json()
        return None

    def count_active(self) -> int:
        with self.lock:
            return sum(
                1 for r in self.records if r.state == STATE_ACTIVE
            )
