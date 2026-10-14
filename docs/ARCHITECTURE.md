# VietSafe architecture (after restructuring)

```text
vietsafe/
├── backend/
│   ├── run.py                 Python launcher
│   ├── vietsafe/
│   │   ├── core/              Pure model, graph, and reference road geometry
│   │   ├── providers/         External upstream API adapters (TomTom, NASA, Open-Meteo)
│   │   ├── web/
│   │   │   ├── controllers/   system, auth, report, admin endpoints
│   │   │   ├── server.py      HTTP Handler, security headers and Host/Origin guard
│   │   │   ├── router.py      URL routing, Request/Response and auth policy
│   │   │   ├── ratelimit.py   In-memory per-IP limiter
│   │   │   └── static.py      Sandbox static file serving
│   │   ├── app.py             Entrypoint
│   │   ├── auth.py            Accounts and sessions
│   │   ├── config.py          Environment and file paths
│   │   ├── db.py              SQLite schema and connection
│   │   ├── reports.py         Citizen reports / verified observations
│   │   └── service.py         DB-to-core orchestration and demo snapshots
│   └── tests/                unittest regression suite
├── frontend/
│   ├── index.html            Site shell and dialogs
│   ├── css/                  CSS layout/themes
│   ├── js/
│   │   ├── main.js           Main ES module
│   │   ├── views/            UI features (app.js contains existing map logic)
│   │   └── data/             API wrapper, DOM tools and example geojson
│   ├── vendor/              Local Leaflet library and license
│   └── tests/                jsdom smoke tests
├── docs/                    Architecture and user/technical DOCX documents
├── scripts/                 Cross-platform launchers and API diagnostics
├── data/                    SQLite created at runtime, Git-ignored
├── Dockerfile
├── render.yaml
├── pyproject.toml
├── package.json
├── requirements.txt
└── requirements-optional.txt
```

## Backend rules

* The application and HTTP server run using only the Python standard library (no Flask or FastAPI). NASA IMERG HDF5 ingestion uses optional third-party `h5py` and its `numpy` dependency: install the optional requirements when needed.
* `core/` contains no database code or live network traffic. Provider HTTP clients are explicitly isolated in `providers/`.
* Controllers own endpoints; routing and role enforcement are centralized. Citizen report creation requires an authenticated session, admin mutations and exports require the admin role, public reads remain public. In-memory per-IP rate limiting is **not** distributed and must not be treated as DDoS protection.
* Static server exposes **only** `frontend/`. Traversal outside its root returns HTTP 404.
* Credentials load from process environment first, then the preserved `.env.local` and `.env` files at the repository root. The original TomTom API key and NASA Earthdata token are included unchanged in this owner-requested package. Git tracking for those credential files is permitted at the owner’s request, but publishing them is unsafe: prefer a private repository or move values into deployment secrets. SQLite starts empty and builds schema on first run.
* User accounts in an earlier SQLite file are **not** automatically migrated. If preserving those records is required, copy the original database to `data/vietsafe.sqlite3` locally before starting.

## Public API ownership

| Controller | Endpoints |
|---|---|
| `system.py` | `/api/health`, `/api/live-status`, `/api/demo/events`, `/api/search`, `/api/weather/forecast`, `/api/gpm/rainfall`, `/api/tomtom/flow/...`, `/api/tomtom/segment`, disabled `/api/snapshot`, `/api/routes` |
| `auth.py` | `/api/auth/me`, `login`, `register`, `logout` |
| `report.py` | `/api/reports` GET/POST; `/api/report-media/<rid>` |
| `admin.py` | `/api/flood/observations` GET/POST, `/api/scenario`, `/api/reports/<rid>`, `/api/export/predictions`, `/api/export/reports` |

## Frontend URL changes

| Old static path | New path |
|---|---|
| `/app.js` | `/js/views/app.js` (loaded via `/js/main.js`) |
| `/map-ai.js` | `/js/views/map-ai.js` (loaded via `/js/main.js`) |
| `/style.css` | `/css/style.css` |
| `/enhancements.css` | `/css/enhancements.css` |
| `/hanoi-boundary.json` | `/js/data/hanoi-boundary.json` |
| `/vendor/leaflet.js` | unchanged |

The original frontend behavior remains concentrated in `js/views/app.js` to reduce regressions while migrating to native modules. `enhancements.js` and `tgcn.js` are retained as **unloaded prototype modules**, as in the uploaded live-only version; they are not trained AI models.

## Scope and known limitations

Real flood depth at road level is unavailable without independent verified observations. Road graph, spatial-rule forecast and example events remain demos; `/api/snapshot` and `/api/routes` still intentionally return disabled statuses. Offline Leaflet **library** does not imply offline background-map tiles. End-to-end user flows and live upstream integrations require browser/manual checks and credentials.

The admin report CSV link is wired in `frontend/js/views/export.js` so it sends its session header instead of opening an unauthorized bare URL.
