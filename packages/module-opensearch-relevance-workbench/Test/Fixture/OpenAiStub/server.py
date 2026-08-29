#!/usr/bin/env python3

"""Deterministic OpenAI-compatible test server for Search Relevance Workbench."""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from typing import Any


DOCUMENT_ID_PATTERN = re.compile(r'"id"\s*:\s*"([^"\\]+)"')
STATE_LOCK = Lock()
STATE: dict[str, Any] = {"calls": 0, "last_model": None}


class Handler(BaseHTTPRequestHandler):
    server_version = "OSRWOpenAIStub/1.0"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._write_json(200, {"status": "ok"})
            return

        if self.path == "/__control__/stats":
            with STATE_LOCK:
                body = dict(STATE)
            self._write_json(200, body)
            return

        self._write_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/__control__/reset":
            with STATE_LOCK:
                STATE.update({"calls": 0, "last_model": None})
            self._write_json(200, {"status": "reset"})
            return

        if self.path != "/v1/chat/completions":
            self._write_json(404, {"error": "not_found"})
            return

        request = self._read_json()
        if request is None:
            return

        messages = request.get("messages")
        if not isinstance(messages, list):
            self._write_json(400, {"error": "messages_required"})
            return

        user_content = "\n".join(
            message.get("content", "")
            for message in messages
            if isinstance(message, dict)
            and message.get("role") == "user"
            and isinstance(message.get("content"), str)
        )
        document_ids = list(dict.fromkeys(DOCUMENT_ID_PATTERN.findall(user_content)))
        ratings = [
            {"id": document_id, "rating_score": 0.9}
            for document_id in document_ids
        ]
        model = request.get("model") if isinstance(request.get("model"), str) else None

        with STATE_LOCK:
            STATE["calls"] += 1
            STATE["last_model"] = model

        content = json.dumps({"ratings": ratings}, separators=(",", ":"))
        self._write_json(
            200,
            {
                "id": "osrw-fixture-completion",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    def log_message(self, format: str, *args: object) -> None:
        return

    def _read_json(self) -> dict[str, Any] | None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._write_json(400, {"error": "invalid_content_length"})
            return None

        if content_length < 1 or content_length > 1_000_000:
            self._write_json(413, {"error": "invalid_body_size"})
            return None

        try:
            body = json.loads(self.rfile.read(content_length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._write_json(400, {"error": "invalid_json"})
            return None

        if not isinstance(body, dict):
            self._write_json(400, {"error": "object_required"})
            return None

        return body

    def _write_json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
