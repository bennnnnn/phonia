#!/usr/bin/env python3
"""Highlight 4xx/5xx from Recall API logs while the app is running.

The API already logs every request (uvicorn access + ``app.http``). This
script watches that stream and prints client/server errors so a 500 in
Learning (or a 401/429) is not buried in 200s.

Success codes (200, 201, 204, 3xx) are ignored. Bodies and auth headers
are never captured — method, path, status, duration, request_id only.

Usage:
  ./scripts/dev.sh watch-errors
  ./scripts/dev.sh api 2>&1 | ./scripts/watch-http-errors.py --passthrough
  ./scripts/watch-http-errors.py --file /tmp/api.log --follow
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

_HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD")
_TRACE_PREFIXES = (
    "Traceback (most recent call last):",
    "The above exception was the direct cause",
    "During handling of the above exception",
    "ExceptionGroup:",
    "  + Exception Group Traceback",
    "  | ",
    "  +-",
)
_MAX_TRACE_LINES = 80


@dataclass(frozen=True)
class Hit:
    method: str
    path: str
    status: int
    duration: str | None = None
    request_id: str | None = None
    source: str = ""


def _leading_status(text: str) -> int | None:
    i = 0
    n = len(text)
    while i < n and text[i] in " \t":
        i += 1
    start = i
    while i < n and text[i].isdigit():
        i += 1
    if i == start or i - start > 3:
        return None
    code = int(text[start:i])
    if 100 <= code <= 599:
        return code
    return None


def _request_id_from(line: str) -> str | None:
    key = "[request_id="
    start = line.find(key)
    if start < 0:
        return None
    start += len(key)
    end = line.find("]", start)
    if end < 0 or end - start > 80:
        return None
    return line[start:end]


def parse_uvicorn(line: str) -> Hit | None:
    """Parse uvicorn access: ``"GET /path HTTP/1.1" 500 ...``."""
    q1 = line.find('"')
    if q1 < 0:
        return None
    q2 = line.find('"', q1 + 1)
    if q2 < 0 or q2 - q1 > 2048:
        return None
    request = line[q1 + 1 : q2]
    space = request.find(" ")
    if space < 0:
        return None
    method = request[:space]
    if method not in _HTTP_METHODS:
        return None
    rest = request[space + 1 :]
    http_at = rest.rfind(" HTTP/")
    path = rest[:http_at] if http_at > 0 else rest
    status = _leading_status(line[q2 + 1 :])
    if status is None:
        return None
    return Hit(method=method, path=path, status=status, source="uvicorn")


def parse_app_http(line: str) -> Hit | None:
    """Parse ``app.http`` access: ``GET /path 500 12.3ms``."""
    if "[app.http]" not in line:
        return None
    msg_at = line.rfind("] ")
    if msg_at < 0:
        return None
    msg = line[msg_at + 2 :].strip()
    space = msg.find(" ")
    if space < 0:
        return None
    method = msg[:space]
    if method not in _HTTP_METHODS:
        return None
    rest = msg[space + 1 :]
    status_at = rest.rfind(" ")
    if status_at < 0:
        return None
    tail = rest[status_at + 1 :]
    maybe_ms = tail.endswith("ms")
    if maybe_ms:
        duration = tail
        rest = rest[:status_at]
        status_at = rest.rfind(" ")
        if status_at < 0:
            return None
        status_s = rest[status_at + 1 :]
        path = rest[:status_at]
    else:
        duration = None
        status_s = tail
        path = rest[:status_at]
    if not status_s.isdigit() or len(status_s) != 3:
        return None
    status = int(status_s)
    if not (100 <= status <= 599):
        return None
    return Hit(
        method=method,
        path=path,
        status=status,
        duration=duration,
        request_id=_request_id_from(line),
        source="app.http",
    )


def parse_json(line: str) -> Hit | None:
    stripped = line.lstrip()
    if not stripped.startswith("{"):
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("event") != "http_request":
        return None
    method = payload.get("method")
    path = payload.get("path")
    status = payload.get("status")
    if not isinstance(method, str) or not isinstance(path, str) or not isinstance(status, int):
        return None
    duration = payload.get("duration_ms")
    duration_s = f"{duration}ms" if isinstance(duration, (int, float)) else None
    rid = payload.get("request_id")
    return Hit(
        method=method,
        path=path,
        status=status,
        duration=duration_s,
        request_id=rid if isinstance(rid, str) else None,
        source="json",
    )


def parse_line(line: str) -> Hit | None:
    return parse_json(line) or parse_app_http(line) or parse_uvicorn(line)


def is_failure(status: int) -> bool:
    return status >= 400


def looks_like_traceback(line: str) -> bool:
    stripped = line.lstrip()
    if line.startswith(_TRACE_PREFIXES) or stripped.startswith(_TRACE_PREFIXES):
        return True
    if stripped.startswith("File ") and ", line " in stripped:
        return True
    if stripped.startswith("ERROR:") or stripped.startswith("ERROR "):
        return True
    if "Error:" in stripped or "Exception:" in stripped:
        return True
    if stripped.startswith("sqlalchemy.") or stripped.startswith("asyncpg."):
        return True
    return False


def _color(enabled: bool, code: str, text: str) -> str:
    if not enabled:
        return text
    return f"\033[{code}m{text}\033[0m"


def format_hit(hit: Hit, *, color: bool) -> str:
    tone = "31" if hit.status >= 500 else "33"
    stamp = datetime.now(tz=timezone.utc).strftime("%H:%M:%S")
    bits = [f"{hit.method} {hit.path}", str(hit.status)]
    if hit.duration:
        bits.append(hit.duration)
    if hit.request_id:
        bits.append(f"request_id={hit.request_id}")
    headline = "  ".join(bits)
    banner = f"── HTTP {hit.status}  {stamp} ──"
    return _color(color, tone, banner) + "\n" + _color(color, tone, headline)


class Watcher:
    def __init__(self, *, passthrough: bool, color: bool, save: TextIO | None) -> None:
        self.passthrough = passthrough
        self.color = color
        self.save = save
        self._trace_left = 0
        self._last_key: tuple[str, str, int] | None = None
        self.failures = 0

    def feed(self, line: str) -> None:
        raw = line.rstrip("\n")
        if self.passthrough:
            sys.stdout.write(line if line.endswith("\n") else line + "\n")
            sys.stdout.flush()
        hit = parse_line(raw)
        if hit is not None:
            self._trace_left = 0
            if not is_failure(hit.status):
                return
            key = (hit.method, hit.path.split("?", 1)[0], hit.status)
            # app.http and uvicorn log the same request — keep one banner.
            if key == self._last_key:
                if hit.status >= 500:
                    self._trace_left = _MAX_TRACE_LINES
                return
            self._last_key = key
            self.failures += 1
            block = format_hit(hit, color=self.color)
            sys.stderr.write(block + "\n")
            sys.stderr.flush()
            if self.save is not None:
                self.save.write(block + "\n")
                self.save.flush()
            if hit.status >= 500:
                self._trace_left = _MAX_TRACE_LINES
            return
        if self._trace_left > 0 and looks_like_traceback(raw):
            self._trace_left -= 1
            sys.stderr.write(raw + "\n")
            sys.stderr.flush()
            if self.save is not None:
                self.save.write(raw + "\n")
                self.save.flush()
        elif self._trace_left > 0 and parse_line(raw) is None and raw.strip() == "":
            return
        elif self._trace_left > 0 and not looks_like_traceback(raw) and raw.strip():
            # Non-trace noise after a 500: stop capturing.
            self._trace_left = 0


def _open_follow(path: Path, *, from_start: bool) -> TextIO:
    handle = path.open(encoding="utf-8", errors="replace")
    if not from_start:
        handle.seek(0, os.SEEK_END)
    return handle


def follow_file(path: Path, watcher: Watcher, *, from_start: bool) -> None:
    while True:
        if not path.exists():
            time.sleep(0.4)
            continue
        with _open_follow(path, from_start=from_start) as handle:
            from_start = True
            while True:
                line = handle.readline()
                if line:
                    watcher.feed(line)
                    continue
                if not path.exists():
                    break
                time.sleep(0.2)


def drain_stdin(watcher: Watcher) -> None:
    for line in sys.stdin:
        watcher.feed(line)


def self_test() -> int:
    uvicorn = (
        'INFO:     127.0.0.1:51814 - "GET /projects/abc HTTP/1.1" 500 Internal Server Error'
    )
    app_http = (
        "2026-08-23 23:30:15,054 INFO [app.http] [request_id=req-1] GET /projects/abc 500 12.3ms"
    )
    ok = 'INFO:     127.0.0.1:1 - "GET /health HTTP/1.1" 200 OK'
    created = 'INFO:     127.0.0.1:1 - "POST /projects HTTP/1.1" 201 Created'
    hit500 = parse_uvicorn(uvicorn)
    hit_app = parse_app_http(app_http)
    assert hit500 is not None and hit500.status == 500 and hit500.path == "/projects/abc"
    assert hit_app is not None and hit_app.request_id == "req-1" and hit_app.duration == "12.3ms"
    assert parse_uvicorn(ok) is not None and not is_failure(parse_uvicorn(ok).status)  # type: ignore[union-attr]
    assert parse_uvicorn(created) is not None and not is_failure(parse_uvicorn(created).status)  # type: ignore[union-attr]
    payload = json.dumps(
        {"event": "http_request", "method": "GET", "path": "/x", "status": 429, "duration_ms": 2}
    )
    hit_json = parse_json(payload)
    assert hit_json is not None and hit_json.status == 429
    print("self-test ok")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print 4xx/5xx from Recall API logs.")
    parser.add_argument(
        "--passthrough",
        action="store_true",
        help="Copy every log line to stdout; errors also go to stderr.",
    )
    parser.add_argument("--file", type=Path, help="Read this log file instead of stdin.")
    parser.add_argument(
        "--follow",
        action="store_true",
        help="With --file, keep reading as new lines arrive (like tail -f).",
    )
    parser.add_argument(
        "--from-start",
        action="store_true",
        help="With --follow, read existing lines first (default is only new lines).",
    )
    parser.add_argument(
        "--save",
        type=Path,
        help="Append highlighted failures (and 5xx tracebacks) to this file.",
    )
    parser.add_argument("--self-test", action="store_true", help="Run parser checks and exit.")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.self_test:
        return self_test()

    color = sys.stderr.isatty()
    save_handle: TextIO | None = None
    if args.save is not None:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        save_handle = args.save.open("a", encoding="utf-8")
    watcher = Watcher(passthrough=args.passthrough, color=color, save=save_handle)
    try:
        if args.file is not None:
            if args.follow:
                follow_file(args.file, watcher, from_start=args.from_start)
            else:
                with args.file.open(encoding="utf-8", errors="replace") as handle:
                    for line in handle:
                        watcher.feed(line)
        else:
            drain_stdin(watcher)
    except KeyboardInterrupt:
        sys.stderr.write("\n")
    finally:
        if save_handle is not None:
            save_handle.close()
        if watcher.failures:
            sys.stderr.write(f"captured {watcher.failures} failed request(s)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
