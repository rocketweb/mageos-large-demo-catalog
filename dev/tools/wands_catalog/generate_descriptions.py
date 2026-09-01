#!/usr/bin/env python3

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SYSTEM_PROMPT = (
    "You write concise, realistic ecommerce catalog copy from supplied facts only. "
    "Do not invent measurements, materials, certifications, compatibility, warranties, brands, "
    "performance claims, or availability. Return only the requested HTML paragraphs."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate resumable WANDS descriptions through oMLX.")
    parser.add_argument("--prompts", required=True, type=Path, help="Description prompt JSON Lines file.")
    parser.add_argument("--output", required=True, type=Path, help="Append-only generated description JSON Lines file.")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8000/v1", help="Loopback OpenAI-compatible endpoint.")
    parser.add_argument("--model", required=True, help="Model name exposed by oMLX.")
    parser.add_argument("--api-key-env", default="OMLX_API_KEY", help="Environment variable containing the API key.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum pending descriptions to attempt.")
    parser.add_argument("--timeout", type=float, default=180.0, help="HTTP timeout in seconds.")
    return parser.parse_args()


def completed_ids(path: Path) -> set[str]:
    completed: set[str] = set()
    if not path.exists():
        return completed
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("status") == "success" and record.get("id") and record.get("description"):
                completed.add(str(record["id"]))
    return completed


def normalize_description(value: str) -> str:
    description = value.strip()
    description = re.sub(r"^```(?:html)?\s*", "", description, flags=re.IGNORECASE)
    description = re.sub(r"\s*```$", "", description)
    if not description:
        raise ValueError("Model returned an empty description")
    if len(description) > 3000:
        raise ValueError("Model returned a description longer than 3,000 characters")
    if re.search(r"<(?!/?p>)[^>]+>", description, flags=re.IGNORECASE):
        raise ValueError("Model returned HTML outside the allowed paragraph tags")
    paragraphs = re.findall(r"<p>(.*?)</p>", description, flags=re.IGNORECASE | re.DOTALL)
    if not 1 <= len(paragraphs) <= 3:
        raise ValueError("Model must return one to three HTML paragraphs")
    if any(not normalized_text_content(paragraph) for paragraph in paragraphs):
        raise ValueError("Model returned an empty paragraph")
    return description


def normalized_text_content(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", value)).strip()


def request_payload(model: str, prompt: str) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.35,
        "max_tokens": 450,
    }


def api_request(url: str, api_key: str, timeout: float, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="GET" if payload is None else "POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def available_models(endpoint: str, api_key: str, timeout: float) -> set[str]:
    response = api_request(f"{endpoint.rstrip('/')}/models", api_key, timeout)
    return {str(item["id"]) for item in response.get("data", []) if isinstance(item, dict) and item.get("id")}


def generate(endpoint: str, api_key: str, model: str, prompt: str, timeout: float) -> str:
    response = api_request(
        f"{endpoint.rstrip('/')}/chat/completions",
        api_key,
        timeout,
        request_payload(model, prompt),
    )
    choices = response.get("choices", [])
    if not choices or not isinstance(choices[0], dict):
        raise ValueError("oMLX returned no completion choices")
    content = choices[0].get("message", {}).get("content")
    if not isinstance(content, str):
        raise ValueError("oMLX returned a completion without text content")
    return normalize_description(content)


def append_record(stream: Any, record: dict[str, Any]) -> None:
    stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def main() -> int:
    arguments = parse_args()
    if arguments.limit is not None and arguments.limit < 1:
        raise SystemExit("--limit must be at least 1")
    api_key = os.environ.get(arguments.api_key_env, "")
    if not api_key:
        raise SystemExit(f"{arguments.api_key_env} is not set")
    models = available_models(arguments.endpoint, api_key, arguments.timeout)
    if arguments.model not in models:
        raise SystemExit(f"Model {arguments.model} is not exposed by the configured oMLX endpoint")

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    lock_path = arguments.output.with_suffix(arguments.output.suffix + ".lock")
    attempted = 0
    with lock_path.open("a+") as lock_stream:
        try:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exception:
            raise SystemExit("Another description generator already owns this output") from exception
        completed = completed_ids(arguments.output)
        with arguments.prompts.open("r", encoding="utf-8") as prompt_stream, arguments.output.open(
            "a", encoding="utf-8"
        ) as output_stream:
            for line_number, line in enumerate(prompt_stream, start=1):
                if arguments.limit is not None and attempted >= arguments.limit:
                    break
                try:
                    prompt_record = json.loads(line)
                except json.JSONDecodeError as exception:
                    raise SystemExit(f"Invalid prompt JSON on line {line_number}") from exception
                record_id = str(prompt_record.get("id", ""))
                prompt = prompt_record.get("prompt")
                if not record_id or not isinstance(prompt, str) or not prompt.strip():
                    raise SystemExit(f"Prompt line {line_number} is missing id or prompt")
                if record_id in completed:
                    continue
                attempted += 1
                started = time.monotonic()
                try:
                    description = generate(arguments.endpoint, api_key, arguments.model, prompt, arguments.timeout)
                    append_record(
                        output_stream,
                        {
                            "id": record_id,
                            "kind": prompt_record.get("kind"),
                            "status": "success",
                            "model": arguments.model,
                            "elapsed_seconds": round(time.monotonic() - started, 3),
                            "description": description,
                        },
                    )
                    completed.add(record_id)
                except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exception:
                    append_record(
                        output_stream,
                        {
                            "id": record_id,
                            "kind": prompt_record.get("kind"),
                            "status": "error",
                            "model": arguments.model,
                            "elapsed_seconds": round(time.monotonic() - started, 3),
                            "error": str(exception)[:500],
                        },
                    )

    print(json.dumps({"attempted": attempted, "completed_total": len(completed)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
