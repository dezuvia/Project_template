#!/usr/bin/env python3
"""Minimal stdio JSON-RPC framing helpers for local MCP-style tools."""

from __future__ import annotations

import json
from typing import BinaryIO


def read_message(stream: BinaryIO) -> dict | None:
    headers: dict[str, str] = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        decoded = line.decode("utf-8")
        name, sep, value = decoded.partition(":")
        if not sep:
            raise ValueError("malformed header line")
        headers[name.strip().lower()] = value.strip()

    length = int(headers.get("content-length", "0"))
    if length <= 0:
        raise ValueError("missing content-length")

    body = stream.read(length)
    if len(body) != length:
        raise ValueError("unexpected EOF while reading message body")
    return json.loads(body.decode("utf-8"))


def write_message(stream: BinaryIO, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    stream.write(header)
    stream.write(body)
    stream.flush()


def make_response(message_id: object, result: dict) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "result": result,
    }


def make_error(message_id: object, code: int, message: str, data: dict | None = None) -> dict:
    error = {
        "code": code,
        "message": message,
    }
    if data is not None:
        error["data"] = data
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": error,
    }
