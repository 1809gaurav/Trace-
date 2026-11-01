"""Validate external engine artifacts before importing them."""

import json
from pathlib import Path
from typing import Any

from jsonschema import ValidationError, validate

from api.errors import APIError

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def validate_real_dependencies() -> None:
    """Require Agent B and both Agent A JSON schemas for real recovery."""
    required = [
        PROJECT_ROOT / "engine" / "pipeline.py",
        PROJECT_ROOT / "schemas" / "results.schema.json",
        PROJECT_ROOT / "schemas" / "custody.schema.json",
    ]
    missing = [str(path.relative_to(PROJECT_ROOT)) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(
            "Real recovery is unavailable because required project files are missing: "
            + ", ".join(missing)
        )


def validate_engine_outputs(results_path: Path, custody_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Parse and validate real engine outputs against project JSON schemas."""
    validate_real_dependencies()
    schema_dir = PROJECT_ROOT / "schemas"
    try:
        results = json.loads(results_path.read_text(encoding="utf-8"))
        custody = json.loads(custody_path.read_text(encoding="utf-8"))
        results_schema = json.loads((schema_dir / "results.schema.json").read_text(encoding="utf-8"))
        custody_schema = json.loads((schema_dir / "custody.schema.json").read_text(encoding="utf-8"))
        validate(instance=results, schema=results_schema)
        validate(instance=custody, schema=custody_schema)
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as error:
        raise APIError(
            422,
            "invalid_engine_output",
            "The recovery output could not be validated. The raw files were kept for review.",
            str(error),
        ) from error
    return results, custody
