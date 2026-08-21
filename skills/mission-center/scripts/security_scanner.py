#!/usr/bin/env python3
"""Minimal, standard-library-only scanner for privacy and secret-like content."""

from __future__ import annotations

import re
from typing import Any

FORBIDDEN_KEY_PATTERN = re.compile(
    r"prompt|tool[-_ ]?args?|raw[-_ ]?logs?|command|secret|password|access[-_ ]?token|bearer|api[-_ ]?key|credential",
    re.IGNORECASE,
)

SECRET_PATTERN = re.compile(
    r"-----BEGIN "
    r"|\b(?:password|secret|token|api[_ -]?key)\s*[:=]\s*\S+"
    r"|\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"
    r"|\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b"
    r"|\b(?:sk|ghp|xox[baprs])[-_][A-Za-z0-9_-]+",
    re.IGNORECASE,
)


# Keep this scanner deliberately small and predictable. These limits make
# malformed or adversarial input a validation error instead of a recursion or
# memory failure.
MAX_SCAN_DEPTH = 1000
MAX_SCAN_NODES = 10000
MAX_SCAN_SCALAR_BYTES = 1_000_000


def scan_forbidden_content(value: Any, path: str = "$") -> list[str]:
    """Scan nested data structures for forbidden field keys and secret-like content."""
    errors: list[str] = []
    stack: list[tuple[Any, str, int]] = [(value, path, 0)]
    nodes = 0
    scalar_bytes = 0
    while stack:
        current, current_path, depth = stack.pop()
        if depth > MAX_SCAN_DEPTH:
            errors.append(f"{current_path} exceeds security scanner depth limit")
            break
        nodes += 1
        if nodes > MAX_SCAN_NODES:
            errors.append(f"{current_path} exceeds security scanner node limit")
            break
        if isinstance(current, dict):
            for key, nested in current.items():
                key_text = str(key)
                scalar_bytes += len(key_text.encode("utf-8", errors="replace"))
                if scalar_bytes > MAX_SCAN_SCALAR_BYTES:
                    errors.append(f"{current_path} exceeds security scanner scalar byte limit")
                    return errors
                nested_path = f"{current_path}.{key_text}"
                if FORBIDDEN_KEY_PATTERN.search(key_text):
                    errors.append(f"{nested_path} is forbidden privacy content")
                if nodes + len(stack) >= MAX_SCAN_NODES:
                    errors.append(f"{current_path} exceeds security scanner node limit")
                    return errors
                stack.append((nested, nested_path, depth + 1))
        elif isinstance(current, list):
            for index in range(len(current) - 1, -1, -1):
                if nodes + len(stack) >= MAX_SCAN_NODES:
                    errors.append(f"{current_path} exceeds security scanner node limit")
                    return errors
                stack.append((current[index], f"{current_path}[{index}]", depth + 1))
        elif isinstance(current, str):
            scalar_bytes += len(current.encode("utf-8", errors="replace"))
            if scalar_bytes > MAX_SCAN_SCALAR_BYTES:
                errors.append(f"{current_path} exceeds security scanner scalar byte limit")
                break
            if SECRET_PATTERN.search(current):
                errors.append(f"{current_path} contains secret-like content")
    return errors
