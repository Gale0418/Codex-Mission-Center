#!/usr/bin/env python3
"""Shared Markdown table parsing with escaped-pipe support.

The parser reads one contiguous table block. Callers choose whether indented
blocks are eligible; a later table is deliberately ignored instead of being
merged into the first table.
"""

from __future__ import annotations

import re
from pathlib import Path

_SEPARATOR = re.compile(r":?-{3,}:?")


def split_cells(line: str) -> list[str]:
    """Split one Markdown table row, honoring ``\\|`` and ``\\\\`` escapes."""
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|") and not text.endswith("\\|"):
        text = text[:-1]
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in text:
        if escaped:
            if char not in ("|", "\\"):
                current.append("\\")
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if escaped:
        raise ValueError("Markdown table row ends with an incomplete escape")
    cells.append("".join(current).strip())
    return cells


def _is_table_line(line: str, include_indented: bool) -> bool:
    return line.lstrip().startswith("|") if include_indented else line.startswith("|")


def first_table_block(lines: list[str], *, include_indented: bool = False) -> list[tuple[int, str]]:
    """Return the first contiguous eligible table block and its one-based lines."""
    block: list[tuple[int, str]] = []
    for number, line in enumerate(lines, start=1):
        if _is_table_line(line, include_indented):
            block.append((number, line.strip()))
        elif block:
            break
    return block


def table_blocks(lines: list[str], *, include_indented: bool = False) -> list[list[tuple[int, str]]]:
    """Return every contiguous eligible Markdown table block with line numbers."""
    blocks: list[list[tuple[int, str]]] = []
    block: list[tuple[int, str]] = []
    for number, line in enumerate(lines, start=1):
        if _is_table_line(line, include_indented):
            block.append((number, line.strip()))
        elif block:
            blocks.append(block)
            block = []
    if block:
        blocks.append(block)
    return blocks


def parse_table_rows(
    lines: list[str],
    *,
    table_name: str,
    include_indented: bool = False,
    strict: bool = True,
) -> tuple[list[dict[str, str]], list[str]]:
    """Parse the first table; strict mode stops at the first malformed row."""
    block = first_table_block(lines, include_indented=include_indented)
    if len(block) < 2:
        return [], [f"{table_name} does not contain a Markdown table"]
    try:
        headers = split_cells(block[0][1])
        separator = split_cells(block[1][1])
    except ValueError as exc:
        return [], [f"{table_name} has malformed Markdown table: {exc}"]
    if not headers or len(separator) != len(headers):
        return [], [f"{table_name} has an invalid table header"]
    if any(not _SEPARATOR.fullmatch(cell) for cell in separator):
        return [], [f"{table_name} has an invalid table separator"]

    rows: list[dict[str, str]] = []
    errors: list[str] = []
    for row_number, (_, line) in enumerate(block[2:], start=1):
        try:
            cells = split_cells(line)
        except ValueError as exc:
            errors.append(f"{table_name} row {row_number} is malformed: {exc}")
        else:
            if len(cells) != len(headers):
                errors.append(f"{table_name} row {row_number} has {len(cells)} cells; expected {len(headers)}")
            else:
                row = dict(zip(headers, cells))
                if any(row.values()):
                    rows.append(row)
        if strict and errors:
            break
    return rows, errors


def parse_table_blocks(
    lines: list[str],
    *,
    table_name: str,
    include_indented: bool = False,
    strict: bool = True,
) -> tuple[list[list[dict[str, str]]], list[str]]:
    """Parse every table block, retaining valid tables in non-strict mode."""
    tables: list[list[dict[str, str]]] = []
    errors: list[str] = []
    for index, block in enumerate(table_blocks(lines, include_indented=include_indented), start=1):
        rows, block_errors = parse_table_rows(
            [line for _, line in block],
            table_name=f"{table_name} table {index}",
            strict=strict,
        )
        if block_errors:
            errors.extend(block_errors)
            if strict:
                break
        else:
            tables.append(rows)
    return tables, errors


def parse_table(
    path: Path,
    *,
    include_indented: bool = False,
    strict: bool = True,
) -> list[dict[str, str]]:
    """Read one table from *path*, raising on malformed input in strict mode."""
    if not path.exists():
        return []
    rows, errors = parse_table_rows(
        path.read_text(encoding="utf-8").splitlines(),
        table_name=path.name,
        include_indented=include_indented,
        strict=strict,
    )
    if errors and strict:
        raise ValueError(errors[0])
    return rows
