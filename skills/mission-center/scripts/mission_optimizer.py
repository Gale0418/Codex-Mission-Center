#!/usr/bin/env python3
"""CLI for project profiling, optimization routing, evaluation, and shadow runs."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from optimization_core import EXPERT_PROFILES, atomic_write_json, build_profile, evaluate_observations, route_profile


def read_json(path: str) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_json_object(path: str) -> dict:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def emit(payload: dict, output: str | None) -> None:
    if output:
        atomic_write_json(Path(output), payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    profile = commands.add_parser("profile")
    profile.add_argument("--input")
    profile.add_argument("--output")
    profile.add_argument("--experts", action="store_true")
    route = commands.add_parser("route")
    route.add_argument("--profile", required=True)
    route.add_argument("--output")
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--manifest", required=True)
    evaluate.add_argument("--observations", required=True)
    evaluate.add_argument("--output")
    shadow = commands.add_parser("shadow")
    shadow.add_argument("--manifest", required=True)
    shadow.add_argument("--observations", required=True, help="Read-only fixture observations; no commands are executed.")
    shadow.add_argument("--workspace", default=".")
    shadow.add_argument("--output")
    args = parser.parse_args()

    if args.command == "profile":
        raw = read_json_object(args.input) if args.input else {}
        payload = build_profile(raw)
        if args.experts:
            payload["expertProfiles"] = EXPERT_PROFILES
        emit(payload, args.output)
    elif args.command == "route":
        emit(route_profile(build_profile(read_json_object(args.profile))), args.output)
    else:
        manifest = read_json_object(args.manifest)
        observations = read_json(args.observations)
        if isinstance(observations, dict):
            observations = observations.get("observations", [])
        result = evaluate_observations(manifest, observations)
        output = args.output
        if args.command == "shadow" and not output:
            experiment_id = str(manifest.get("experimentId", "experiment"))
            if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", experiment_id):
                raise ValueError("experimentId must be a safe 1-64 character filename identifier")
            output = str(Path(args.workspace).resolve() / "output" / "mission-center-optimization" / f"{experiment_id}-result.json")
        emit(result, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
