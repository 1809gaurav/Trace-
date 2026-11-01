"""Unit tests sharing the production ``engine`` package namespace."""

from pathlib import Path

__path__.append(str(Path(__file__).resolve().parents[2] / "engine"))
