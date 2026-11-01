"""Regenerate the checked-in JSON Schema files."""

from schemas.models import export_json_schemas


if __name__ == "__main__":
    export_json_schemas()
