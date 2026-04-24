# Hydrex Form Assistant

Hydrex Form Assistant is a local-first internal web app for collecting HUD environmental worksheet intake data and automating **data gathering support** for:

- Explosive and Flammable Hazards
- Contamination and Toxic Substances

> **Required Disclaimer:** This tool assists with data gathering and draft language generation only. All environmental determinations must be reviewed and approved by qualified Hydrex Environmental staff.

## Features

- Single-screen dashboard with project intake + generated outputs.
- SQLite project persistence (save/load/export).
- Address geocoding through OpenStreetMap Nominatim.
- Buffer generation for 0.5-mile and 1-mile review areas.
- EPA ECHO integration (best-effort API call with graceful failure handling).
- TCEQ workflow support via uploaded CSV dataset (PST/LPST filtering by distance).
- GIS-style map view (Leaflet) with project point and buffer overlays.
- Automated Data Results cards:
  - RCRA sites within 0.5 mile
  - LPST sites within 0.5 mile
  - PST sites within 1 mile
  - nearest facility distance
  - sources used
- Smart auto-fill suggestion when no nearby sites are found.
- Evidence checklist generator and missing item highlighting.
- Source tracking with timestamps.
- Draft worksheet language generator upgraded with count + distance references.

## API/Data Sources

- **OpenStreetMap Nominatim** for geocoding.
- **EPA ECHO (FRS facility search endpoint)** for nearby facilities and compliance context.
- **TCEQ data** via CSV upload (public dataset export, manual extract, or internal reference file).

## How data is gathered

1. User enters address/project fields.
2. User clicks **Run Environmental Search**.
3. App geocodes address if lat/long missing.
4. App computes 0.5-mile and 1-mile buffers.
5. App queries EPA ECHO with lat/long and radius.
6. App parses optional uploaded TCEQ CSV and filters by distance.
7. App stores structured results JSON, source-tracking JSON, and buffer metadata in SQLite.
8. User reviews, manually overrides if needed, then generates worksheet draft text.
Hydrex Form Assistant is a local-first internal web app for collecting project intake data and drafting language for HUD environmental worksheets.

## Features

- Single-screen dashboard UI for intake + outputs.
- SQLite-backed project save/load workflow.
- Intake fields for project, hazard, contamination, and evidence documentation.
- Draft generation for:
  - Explosive and Flammable Hazards
  - Contamination and Toxic Substances
- Missing evidence checklist generation.
- Copy-to-clipboard for each generated summary.
- Export project report as Markdown.
- Internal-use disclaimer requiring qualified staff review.

## Tech Stack

- Python 3
- Flask
- SQLite
- Vanilla HTML/CSS/JavaScript
- Leaflet (map UI)

## Install

1. Ensure Python 3.10+ is installed.
2. Create and activate virtual environment:
2. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Run

```bash
./start.sh
```

`start.sh` now runs a quick syntax check (`python3 -m py_compile app.py`) before launching, so startup errors are surfaced early.

Open locally: <http://127.0.0.1:8080>

LAN access:

- `http://<your-server-lan-ip>:8080` (example: `http://192.168.1.69:8080`)

Override host/port:

```bash
HOST=0.0.0.0 PORT=8080 ./start.sh
```

## Run as a service (systemd)

A systemd unit template is provided at:

- `deploy/systemd/hydrex-form-assistant.service`

Install/start with:

```bash
sudo ./scripts/install_service.sh
```

Manual commands (if preferred):

```bash
sudo cp deploy/systemd/hydrex-form-assistant.service /etc/systemd/system/hydrex-form-assistant.service
sudo sed -i "s|__SERVICE_USER__|$USER|g" /etc/systemd/system/hydrex-form-assistant.service
sudo sed -i "s|__WORKDIR__|$(pwd)|g" /etc/systemd/system/hydrex-form-assistant.service
sudo systemctl daemon-reload
sudo systemctl enable hydrex-form-assistant
sudo systemctl start hydrex-form-assistant
sudo systemctl status hydrex-form-assistant
```

Follow logs:

```bash
sudo journalctl -u hydrex-form-assistant -f
```

If service mode fails, validate app syntax directly:

```bash
python3 -m py_compile app.py
```

## Seed sample project
## Seed sample project
If you need a different port:

```bash
PORT=7000 ./start.sh
```

Then open locally: <http://127.0.0.1:8080>

For LAN access from another device on your network, use:

- `http://<your-server-lan-ip>:8080` (example: `http://192.168.1.69:8080`)

You can also override host/port explicitly:

```bash
HOST=0.0.0.0 PORT=8080 ./start.sh
```

## Seed sample project
Then open: <http://127.0.0.1:8080>
Then open: <http://127.0.0.1:6000>
Then open: <http://127.0.0.1:5000>

## Seed a Sample Project

```bash
python3 seed_sample_project.py
```

This inserts **Maple Court Rehab** with example environmental pull metadata and generated-ready counts.

## Example project for successful data pull

After seeding, load **Maple Court Rehab** from the Saved Projects dropdown. It includes:

- lat/long and buffers
- RCRA/LPST/PST counts
- nearest facility distance
- source tracking timestamps
- evidence checklist completion

## TCEQ sample dataset format

A sample CSV is included at `data/tceq_sample.csv`:

```csv
name,type,status,latitude,longitude
North Storage Yard,PST,Active,31.114,-97.756
Maple Fuel Depot,LPST,Investigating,31.109,-97.742
Old Service Station,LPST,Closed,31.100,-97.749
```

## Service-layer modules

TypeScript service modules are included for modular workflow reference:

- `services/geocode.ts`
- `services/epa.ts`
- `services/tceq.ts`
- `services/spatial.ts`

These return structured JSON-style objects and mirror the backend workflow design.

## Storage

- SQLite DB: `hydrex_form_assistant.db`
- Markdown exports: `exports/`
A sample project named **Maple Court Rehab** will be inserted into the SQLite database.

## Data Storage

- SQLite file: `hydrex_form_assistant.db`
- Markdown exports: `exports/`

## Notes

This app does **not** make final environmental determinations. Generated text must be reviewed and finalized by qualified Hydrex staff before submission.
