# Trace

Trace is an evidence-recovery frontend and a local FastAPI backend demo. The React UI remains in the repository root; the backend lives under `api/`.

## Run the application

Requirements: Python 3.11+ and Node.js/npm.

1. Copy `.env.example` to `.env`. The example selects the fake engine and disables the frontend mock client.
2. Install backend dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Start the all-in-one demo:

   ```powershell
   python run_demo.py --prerun
   ```

   This migrates the database, builds the existing Vite app with its real API client enabled, seeds a clearly synthetic image if `testdata/demo_mixed/disk.img` is absent, optionally runs it through the fake engine, and serves the app/API at `http://127.0.0.1:8000`.

To develop only the frontend, run `npm install` and `npm run dev`. Vite proxies `/api` and WebSocket requests to `http://127.0.0.1:8000`. Set `VITE_USE_MOCK=true` to retain the original in-memory frontend mock. `VITE_USE_MOCK=false` selects the backend. `VITE_API_URL` may be a relative `/api` URL or an absolute API base URL.

Other useful commands:

```powershell
python run_demo.py
python run_demo.py --reset --prerun
python -m pytest -q
npm run lint
npm run build
```

The Makefile also provides `make dev`, `make test`, and `make demo` in environments with `make`.

## API

Interactive OpenAPI documentation is available at `/docs`.

| Method | Path | Purpose |
|---|---|---|
| GET, POST | `/api/cases` | List recent live cases; create a case |
| GET, DELETE | `/api/cases/{case_id}` | Get a case and latest evidence; soft-delete without deleting evidence |
| POST | `/api/cases/{case_id}/upload` | Stream, hash, and lock an evidence image |
| POST | `/api/cases/{case_id}/ground-truth` | Attach benchmark metadata when `DEMO_MODE=true` |
| POST, GET | `/api/cases/{case_id}/runs` | Queue a run; list past runs |
| POST | `/api/cases/{case_id}/runs/{run_id}/cancel` | Cancel a queued or active run |
| GET | `/api/cases/{case_id}/runs/{run_id}/events` | Replay persisted events after `after_seq` |
| WS | `/api/ws/cases/{case_id}` | Receive and replay progress events |
| GET | `/api/cases/{case_id}/results` | Filter and page recovered-file results |
| GET | `/api/cases/{case_id}/score` | Read a synthetic benchmark score, when available |
| GET | `/api/cases/{case_id}/files/{public_id}` | Get file details |
| GET | `/api/cases/{case_id}/files/{public_id}/content` | Download a case-owned output; supports a single byte range |
| GET | `/api/cases/{case_id}/files/{public_id}/preview` | Inline image or generated preview |
| GET | `/api/cases/{case_id}/files/{public_id}/hex` | Bounded hex/ASCII view into the original evidence |
| GET | `/api/cases/{case_id}/custody` | Read the append-only custody entries |
| GET | `/api/cases/{case_id}/verify` | Verify seals and audit the verification without changing the chain |
| POST | `/api/cases/{case_id}/tamper-demo` | Verify a changed in-memory copy; stored custody is untouched |
| POST, GET | `/api/cases/{case_id}/report` | Generate a report; download the latest PDF |
| GET | `/api/cases/{case_id}/report/preview` | Preview the report as HTML |
| GET | `/api/health`, `/api/version` | Health and version information |
| POST | `/api/auth/login` | Issue a JWT when `AUTH_MODE=jwt` |

JSON request/response field names use `snake_case`; the adapter in `src/api/mappers.ts` translates to the existing UI types. HTTP errors use `{ "error": { "code", "message", "details" } }`. Responses carry `X-Trace-Engine`, `X-Request-ID`, and `X-Content-Type-Options`.

## Configuration and evidence safety

Configuration is loaded by `api/config.py` from environment variables or `.env`: data directory, database URL, upload/request limits, CORS origins, engine/auth modes, job concurrency/timeout, report engine, and frontend serving. SQLite connections enable WAL and foreign keys; other SQLAlchemy URLs can be used without SQLite-specific query code.

Evidence uploads are streamed in 1 MiB chunks, hashed while writing, atomically moved below `DATA_DIR/evidence`, and marked read-only where the platform supports it. Runs hash the stored image before and after processing. Case deletion is soft; custody entries have no update/delete API. File/report paths are resolved and checked to remain under the configured data directory.

`AUTH_MODE=none` is for local demos only. `apikey` requires `API_KEY`; `jwt` requires `JWT_SECRET`, `DEMO_USERNAME`, and `DEMO_PASSWORD`. The seeded JWT account is stored with an Argon2 password hash. Do not put production credentials in Vite environment variables; `VITE_API_KEY` and `VITE_API_TOKEN` are development/demo conveniences that become public in a browser build.

## Engine and current integration limits

`ENGINE_MODE=fake` is intentionally labelled in API responses and writes synthetic output strings; it does not recover the uploaded image. `run_demo.py --prerun` caches a fake run unless the configured real engine is available.

This checkout currently has no `engine/`, `custody/`, `scorer/`, `schemas/`, `testgen/`, or `testdata/` directories. Accordingly, real mode refuses to run unless Agent B's CLI and the results/custody schemas are present; the real scorer and Agent B custody verification cannot be integrated or certified yet. The initial migration and fake API flow do run without those assets.

The frontend components were not changed. Its current custody tamper controls remain local-only, it has no visible "Demo data" badge or a dedicated unavailable-score state, and it does not provide a login UI. These are suggested UI follow-ups; the API exposes engine mode and error codes for them.

## Tests

The backend tests cover empty-database migration, DB/API case upload, streamed 128 MiB upload memory, expected-hash/empty-upload rejection, fake run completion and event replay over WebSocket, cancellation, score, custody tamper immutability, bounded hex access, report PDF generation and chain extension, soft deletion, and API-key/JWT basics. The 128 MiB streaming test asserts traced Python allocations stay below 16 MiB. Real-engine, schemas, and ground-truth scoring tests cannot run until their source assets are supplied.
