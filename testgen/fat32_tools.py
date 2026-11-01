"""Optional external FAT32 validation using fsck.fat and mtools."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import warnings
from pathlib import Path
from typing import Callable


def validate_saved(
    path: str | Path, names: list[str], read_file: Callable[[str], bytes],
    validate_internal: Callable[[], None],
) -> None:
    """Run filesystem checks and compare every mcopy extraction to source bytes."""
    fsck, mdir, mcopy = (shutil.which(tool) for tool in ("fsck.fat", "mdir", "mcopy"))
    if not fsck or not mdir or not mcopy:
        missing = [
            name for name, found in (("fsck.fat", fsck), ("mdir", mdir), ("mcopy", mcopy))
            if not found
        ]
        warnings.warn(
            f"skipping external FAT32 validation; missing: {', '.join(missing)}; "
            "internal re-parse validation was used",
            RuntimeWarning,
        )
        validate_internal()
        return
    image_path = Path(path)
    check = subprocess.run([fsck, "-n", str(image_path)], capture_output=True, text=True, check=False)
    if check.returncode:
        raise RuntimeError(f"fsck.fat validation failed: {check.stdout}\n{check.stderr}")
    listing = subprocess.run(
        [mdir, "-i", str(image_path), "::"], capture_output=True, text=True, check=False
    )
    if listing.returncode:
        raise RuntimeError(f"mdir validation failed: {listing.stderr}")
    with tempfile.TemporaryDirectory(
        prefix=".mcopy-check-", dir=image_path.parent
    ) as temporary:
        for name in names:
            destination = Path(temporary) / Path(name).name
            extracted = subprocess.run(
                [mcopy, "-i", str(image_path), f"::{name}", str(destination)],
                capture_output=True, text=True, check=False,
            )
            if extracted.returncode or destination.read_bytes() != read_file(name):
                raise RuntimeError(f"mcopy validation failed for {name}: {extracted.stderr}")
