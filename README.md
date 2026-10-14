# VietSafe — modular edition

VietSafe is a local-first flood and traffic prototype. The repository has been reorganized into **Python 3.10+ stdlib backend** and **HTML/CSS/ES module frontend** while preserving its existing API contract and locally bundled Leaflet library.

## Run on macOS / Linux

```bash
sh scripts/start.sh
# or: python3 backend/run.py --port 8765
```

## Run on Windows

Double-click `scripts/START-VIETSAFE.cmd`, or:

```powershell
python backend/run.py --port 8765
```

Open **http://127.0.0.1:8765/**. Python dependencies are **not required** for the HTTP server, SQLite, TomTom proxy, or Open-Meteo JSON integration. Accessing remote maps or upstream APIs does require network connectivity; Leaflet itself works offline.

## Credentials and configuration (preserved from the uploaded project)

**The original `TOMTOM_API_KEY` and `NASA_EARTHDATA_TOKEN` have been retained**
unchanged in `vietsafe/.env` in this distribution, so you do not need to enter
those two values again. The original `.env.local` is also retained; it has no
administrator password configured. The backend reads them from the repository
root automatically via `backend/vietsafe/config.py`. Explicit process environment
variables take precedence over `.env.local`, then `.env`.

Check that the keys can be loaded (keys are **not printed**):

```bash
python3 scripts/kiem_tra_tomtom.py
python3 scripts/kiem_tra_nasa.py
```

Create first administrator (the source SQLite has no built-in admin account):

```bash
python3 scripts/create_admin.py
```

Optional live connectivity checks, requiring Internet and applicable service permissions:

```bash
python3 scripts/kiem_tra_tomtom.py --live
python3 scripts/kiem_tra_nasa.py --online
```

These local checks verify configuration presence; **they do not by themselves
prove that upstream APIs have granted access**. The NASA GPM raw HDF5 integration
needs the optional packages from `requirements-optional.txt`, and a NASA 403 may
also reflect missing GES DISC permissions or an expired token.

**Important security risk:** You previously requested Git to track the configured
API tokens, so `.gitignore` in this distribution permits `.env` and `.env.local`.
If you commit these files and push to a PUBLIC GitHub repository, anyone can
copy these credentials; deleting the file from a later commit does not remove
it from Git history. A PRIVATE repository or host-side secret manager is
strongly advised. These files remain excluded from the Docker *image* by
`.dockerignore`; Docker runtime needs `--env-file .env` and Render deployments
need explicit Environment variables (Git doesn't automatically configure them).
Do not put a real `VIETSAFE_ADMIN_PASSWORD` into a publicly tracked file.


## Tests

```bash
python -m unittest discover -s backend/tests -v
# optional frontend tests (requires npm install for jsdom):
npm install
npm test
```

## Deployment

```bash
docker build --build-arg ENABLE_NASA=1 -t vietsafe .
docker run --rm -p 8765:8765 --env-file .env vietsafe
```

Set credentials using deployment environment variables for Render or Docker. Build without `--build-arg ENABLE_NASA=1` for a stdlib-only image; this option installs HDF5 dependencies needed for NASA. For a custom reverse-proxy hostname, set `VIETSAFE_ALLOWED_HOSTS` to comma-separated hostname(s). Proxy/routing behavior must be configured and tested separately.

See `docs/ARCHITECTURE.md` for the new tree, route ownership, static URL mapping, migration notes, and known limitations. Older documents under `docs/legacy/` predate this reorganization and may show obsolete paths or insecure credential tracking instructions.

## Audit and known gaps

See `docs/AUDIT_2026-10-14.md` for verified fixes and unfinished research/product functionality, including no real road-depth measurements and no trained T-GCN.
