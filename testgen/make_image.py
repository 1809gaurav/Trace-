"""Command-line entry point for deterministic scenario images."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

from testgen.scenarios import SCENARIOS, build_scenario


def generate(
    out: str | Path = "testdata", *, seed: int = 1337,
    only: Sequence[str] | None = None,
) -> dict[str, dict[str, object]]:
    """Generate selected scenarios and return their ground-truth summaries."""
    root = Path(out)
    if only is None:
        selected = list(SCENARIOS)
    else:
        selected = []
        for requested in only:
            requested = requested.strip()
            name = next(
                (scenario for scenario, letter in SCENARIOS.items()
                 if requested.lower() in (scenario.lower(), letter.lower())),
                None,
            )
            if name is None:
                raise ValueError(f"unknown scenario selector: {requested}")
            if name not in selected:
                selected.append(name)
    summaries = {}
    for name in selected:
        truth = build_scenario(name, root / name, seed)
        path = root / name / "disk.img"
        image_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        truth_path = root / name / "ground_truth.json"
        if json.loads(truth_path.read_text(encoding="utf-8"))["image"]["sha256"] != image_sha:
            raise RuntimeError(f"ground-truth image hash mismatch for {name}")
        summaries[name] = {
            "files": len(truth["files"]),
            "deleted": sum(item["state"] in (
                "deleted_contiguous", "deleted_fragmented", "dvr_deleted"
            ) for item in truth["files"]),
            "fragmented": sum(len(item["fragments"]) > 1 for item in truth["files"]),
            "decoys": len(truth["decoys"]),
            "sha256": image_sha,
        }
    return summaries


def main(argv: Sequence[str] | None = None) -> int:
    """Run the image generator CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("testdata"))
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument(
        "--only", type=lambda value: value.split(","),
        help="comma-separated scenario letters A-F or scenario names",
    )
    args = parser.parse_args(argv)
    summaries = generate(args.out, seed=args.seed, only=args.only)
    print(f"{'SCENARIO':<16} {'FILES':>5} {'DELETED':>7} {'FRAG':>5} {'DECOYS':>6}  SHA256")
    for name, summary in summaries.items():
        print(
            f"{name:<16} {summary['files']:>5} {summary['deleted']:>7} "
            f"{summary['fragmented']:>5} {summary['decoys']:>6}  {summary['sha256']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
