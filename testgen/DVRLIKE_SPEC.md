# DVRX synthetic container specification

`DVRX` is a deliberately small, documented test format. It is not a real DVR
vendor format and must not be interpreted as one.

All integers are unsigned little-endian. The file begins with a 12-byte header:

| Offset | Size | Field | Value |
|---:|---:|---|---|
| 0 | 4 | magic | ASCII `DVRX` |
| 4 | 2 | version | `1` |
| 6 | 2 | channel | channel number |
| 8 | 4 | reserved | zero |

The header is followed immediately by frame records until EOF. Each record
contains a 20-byte header, payload, and 4-byte checksum:

| Record offset | Size | Field |
|---:|---:|---|
| 0 | 4 | ASCII `FRM0` |
| 4 | 4 | frame index, starting at zero |
| 8 | 8 | Unix timestamp in milliseconds |
| 16 | 4 | payload length in bytes |
| 20 | `payload length` | JPEG frame payload |
| after payload | 4 | CRC-32/ISO-HDLC of the payload |

Clips contain 20–40 JPEG frames at strictly increasing one-second intervals.
Frames are generated at 160×120 and are expected to be 2–4 KiB. Clip metadata
records `frame_count`, `start_time`, and `end_time` in ISO-8601 UTC. Clip names
use a long FAT filename such as `CH01_0001.DVR`; the FAT writer creates a VFAT
long-name entry and a compatible 8.3 alias.

Parser implementations should reject truncated record headers, payloads, and
CRC fields; validate the frame magic, monotonically increasing timestamp, and
payload CRC; and report offsets as absolute offsets into the containing image.
