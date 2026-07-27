"""Measure planning normalization without declaring universal performance limits."""
from __future__ import annotations

import argparse
import json
import sys
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.planning import normalize_inventory  # noqa: E402


def synthetic_ways(count: int, points: int) -> list[dict]:
    types = ("primary", "secondary", "tertiary", "residential", "unclassified")
    return [
        {
            "type": types[index % len(types)],
            "name": f"Calle {index // 4}",
            "len": 0.1 + index % 20 / 100,
            "geom": [
                {"lat": 40 + point / 10000, "lon": -3 - index / 100000 - point / 10000}
                for point in range(points)
            ] if index % 7 else None,
        }
        for index in range(count)
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ways", type=int, default=51_176)
    parser.add_argument("--points-per-way", type=int, default=12)
    parser.add_argument("--input-json", type=Path)
    parser.add_argument("--max-seconds", type=float)
    parser.add_argument("--max-peak-mb", type=float)
    parser.add_argument("--max-output-mb", type=float)
    args = parser.parse_args()

    if args.input_json:
        source = json.loads(args.input_json.read_text(encoding="utf-8"))
        ways = source.get("ways", source) if isinstance(source, dict) else source
        if not isinstance(ways, list):
            raise SystemExit("Input JSON must be a list or contain a ways list")
    else:
        ways = synthetic_ways(args.ways, args.points_per_way)

    input_bytes = len(json.dumps(ways, separators=(",", ":")).encode())
    tracemalloc.start()
    started = time.perf_counter()
    inventory = normalize_inventory("benchmark", ways)
    output_bytes = len(json.dumps(inventory, separators=(",", ":")).encode())
    duration = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    metrics = {
        "records": len(ways),
        "input_mb": round(input_bytes / 1024 / 1024, 2),
        "output_mb": round(output_bytes / 1024 / 1024, 2),
        "seconds": round(duration, 3),
        "peak_mb": round(peak / 1024 / 1024, 2),
        "groups": len(inventory["groups"]),
        "targets": len(inventory["targets"]),
        "hash": inventory["base_inventory_hash"],
    }
    print(json.dumps(metrics, indent=2))

    failed = (
        (args.max_seconds is not None and duration > args.max_seconds)
        or (args.max_peak_mb is not None and peak / 1024 / 1024 > args.max_peak_mb)
        or (args.max_output_mb is not None and output_bytes / 1024 / 1024 > args.max_output_mb)
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
