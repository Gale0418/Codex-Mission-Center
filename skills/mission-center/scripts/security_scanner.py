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
    r"-----BEGIN |(?:password|secret|api[_ -]?key)\s*=|\b(?:sk|ghp|xox[baprs])[-_][A-Za-z0-9_-]+",
    re.IGNORECASE,
)


def scan_forbidden_content(value: Any, path: str = "$") -> list[str]:
    """Scan nested data structures for forbidden field keys and secret-like content."""
    errors: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            if FORBIDDEN_KEY_PATTERN.search(str(key)):
                errors.append(f"{path}.{key} is forbidden privacy content")
            errors.extend(scan_forbidden_content(nested, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            errors.extend(scan_forbidden_content(nested, f"{path}[{index}]"))
    elif isinstance(value, str) and SECRET_PATTERN.search(value):
        errors.append(f"{path} contains secret-like content")
    return errors
