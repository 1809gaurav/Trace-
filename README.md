# Trace (ForensicRecover)

Trace combines a deterministic FAT32/DVR-like fixture generator, a read-only
recovery engine, versioned JSON contracts, an independent recovery scorer, a
local FastAPI service, and a React frontend. Evidence images are ordinary files:
the application does not mount them, and recovery opens them read-only.

## Requirements and setup

- Python 3.11 or newer and Node.js/npm
- Install all Python dependencies with `python -m pip install -r requirements-dev.txt`
- Install frontend dependencies with `npm ci`
- Optional FAT validation tools: `fsck.fat`, `mdir`, and `mcopy`

No disk is mounted and no root privileges are needed. Generated fixture
timestamps and random content are fixed by the selected seed.

## Run Trace locally

Copy `.env.example` to `.env`, configure the local API key, then start the
single-process demo:

```powershell
python run_demo.py
```

The service binds to `127.0.0.1:8000`, runs database migrations, and serves the
frontend and API. `python run_demo.py --reset` clears only the known demo-data
children below `DATA_DIR`; `--prerun` additionally seeds and runs the demo case.
Do not use synthetic demo output as recovered evidence. For frontend-only
development, use `npm run dev`. Set `VITE_USE_MOCK=true` only when intentionally
using the in-memory frontend mock; the API client is the normal configuration.

The API's interactive documentation is served at `/docs`. Its main endpoints
cover cases and uploads, recovery runs and event replay, results and files,
custody verification, scoring, and report generation. Authentication and engine
mode are controlled by `.env`; fake mode is intended only for explicitly
synthetic demo runs.

## Generate test images

```powershell
python -m testgen.make_image --out testdata --seed 1337
python -m testgen.make_image --out testdata --seed 7 --only A,C
```

`--only` accepts comma-separated scenario letters (`A`–`F`) or names. A
`testdata/<scenario>/` directory contains `disk.img`, `ground_truth.json`, and
`originals/`. The command prints file/deletion/fragment/decoy counts and the
image SHA-256 for each generated scenario. Repeating a generation with the
same seed produces the same image bytes.

The FAT32 writer creates 128 MiB images, uses 512-byte sectors and 1 KiB
clusters, and supports VFAT long names plus 8.3 names. It validates image
structure and reads its files back internally before destructive edits. When
all three optional external tools exist, it also runs `fsck.fat -n` and
extracts each pristine file with `mcopy`; otherwise it emits a warning and
uses the internal re-parse check.

### Scenario composition

| Letter | Directory | Contents |
|---|---|---|
| A | `clean_deleted` | 8 JPEG, 3 PDF, and 2 PNG files; 6 deleted contiguously, 7 live. |
| B | `corrupted_fs` | The same 13 files; root directory cluster zeroed and the first 30% of each FAT copy replaced with seeded bytes. |
| C | `fragmented` | 6 deleted JPEGs (3 contiguous and 3 split into two fragments with noise-filled gaps), plus one deleted three-fragment stretch file marked unrecoverable. |
| D | `demo_mixed` | 15 recoverable files: 6 intact deleted media, 5 carved files, 2 two-fragment JPEGs, and 2 DVRX clips (one live and one deleted); plus 2 unrecoverable overwritten JPEGs and 5 decoys (2 gap-noise regions and 3 malformed/signature decoys). The first 30% of both FAT copies, excluding reserved entries, is damaged without changing the boot sector or root directory. |
| E | `empty_fs` | A valid empty FAT32 volume. |
| F | `not_fat` | 1 MiB of seeded random bytes; ground truth declares `unrecognized_filesystem`. |

The synthetic DVRX container is specified in
[testgen/DVRLIKE_SPEC.md](testgen/DVRLIKE_SPEC.md). It is not a real vendor
format.

## Run the recovery engine

```powershell
python -m engine.pipeline `
  --image testdata/demo_mixed/disk.img `
  --out out `
  --progress jsonl
```

The engine opens evidence read-only, hashes it before and after processing,
and writes `results.json`, `custody.json`, and recovered files under `out/`.
It validates FAT32 directory recovery, signature carving, and bounded
two-fragment JPEG reconstruction before classifying each result. Unknown-size
JPEG fragment searches have stricter limits than searches backed by directory
metadata. The engine does not import the generator or scorer.

## Shared JSON schemas

Pydantic v2 models in `schemas/models.py` are the source of truth. Regenerate
the checked-in schemas after a contract change:

```powershell
python -m schemas.export_schemas
```

- `results.schema.json`: engine output, including absolute, end-exclusive
  image offsets and per-file classifications/confidence.
- `custody.schema.json`: a JSON array of hash-chained custody entries. Each
  hash is `SHA256(prev_hash + step + canonical_json(details))`; canonical JSON
  sorts keys and uses compact separators. `compute_entry_hash()` implements
  this rule.
- `ground_truth.schema.json`: generator output with original hashes,
  allocation fragments, state, expected route/classification, metadata, and
  decoys.
- `score.schema.json`: scorer metrics, per-file statuses, and calibration
  buckets.

Examples live in `schemas/examples/`. Contract field names use `snake_case`.

## Score a recovery

```powershell
python -m scorer.score `
  --truth testdata/clean_deleted/ground_truth.json `
  --results results.json `
  --recovered-dir out `
  --image testdata/clean_deleted/disk.img `
  --json score.json `
  --strict
```

The scorer validates both inputs before scoring and prints field-level schema
errors. `--strict` returns a non-zero status if the image hash differs from
ground truth or if schema validation fails. A score is also written to
`score.json` by default.

Matching is one-to-one. SHA-256 equality is an exact match; otherwise a result
is a partial match if its image offsets overlap at least 50% of the original
size or if at least 50% of its 512-byte blocks match at the same relative
positions. Completeness is the matching-block fraction at those same relative
positions. The scorer builds a SHA-256-to-original-block-index dictionary,
looks up recovered blocks in order, and counts a block only when its index
matches the original index and advances beyond the prior match. Fragment
originals are reconstructed in ground-truth file order from the declared
image ranges. Duplicate matches, decoys, and unrelated items count as false
positives.

Metric definitions:

- `precision = true positives / (true positives + false positives)`
- `recall = exact matches / recoverable ground-truth files`
- `completeness = mean completeness over recoverable files (misses are 0)`
- `false_positive_rate = false positives / all recovered items`
- `metadata_accuracy` counts correct names, FAT timestamps (±2 seconds), and
  DVR frame count/times (exact count, ±1 second) over all applicable values.
- `classification_accuracy` counts matched results whose classification is
  in the ground truth's acceptable list.
- `calibration` reports the correct-item rate in confidence buckets
  `[0,.3)`, `[.3,.5)`, `[.5,.7)`, `[.7,.85)`, and `[.85,1]`.

## Tests

```powershell
python -m pytest -q
npm run lint
npm run build
```

Tests also use Python's built-in `unittest` runner and can be run without
pytest:

```powershell
python -m unittest discover -s tests -v
```

See [docs/BASELINE.md](docs/BASELINE.md) for the measured seed-1337 A–F
pre-integration engine/scorer baseline. It is a tuning baseline, not a holdout
result. The synthetic DVRX container in
[testgen/DVRLIKE_SPEC.md](testgen/DVRLIKE_SPEC.md) is not a real vendor format.
