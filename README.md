# Hydrex Form Assistant

Hydrex Form Assistant is a local-first Flask app for HUD-style environmental review support.

> **Disclaimer:** This tool assists with data gathering and draft language generation only. All environmental determinations must be reviewed and approved by qualified Hydrex Environmental staff.

## Capabilities

- Project save/load with SQLite
- Geocoding (Nominatim)
- 0.5-mile and 1-mile buffer workflow
- EPA ECHO facility search (optional via env)
- TCEQ CSV + optional ArcGIS layer ingest
- Leaflet map with project/buffers/RCRA/LPST/PST markers
- Selected assessed tank workflow
- HUD answer engine for:
  - Explosive and Flammable Hazards
  - Contamination and Toxic Substances
- Evidence checklist generation
- Draft summary language generation
- Markdown and PDF report exports

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
./start.sh
```

Open: `http://127.0.0.1:8080`

## Environment variables

- `PORT` (default from `DEFAULT_PORT`)
- `DEFAULT_PORT` (default `8080`)
- `HOST` (default `0.0.0.0`)
- `EPA_ECHO_ENABLED` (`true`/`false`, default `true`)
- `TCEQ_ARCGIS_LAYER_URL` (optional ArcGIS FeatureServer layer URL)

Example:

```bash
HOST=0.0.0.0 PORT=8080 EPA_ECHO_ENABLED=true ./start.sh
```

## Service (systemd)

```bash
sudo ./scripts/install_service.sh
sudo systemctl status hydrex-form-assistant
```

## Seed sample project

```bash
python3 seed_sample_project.py
```

## Data source notes

- **Nominatim**: address -> lat/lon
- **EPA ECHO**: nearby facility/compliance context
- **TCEQ CSV**: manual dataset upload for LPST/PST/tank screening
- **ArcGIS (optional)**: if `TCEQ_ARCGIS_LAYER_URL` is configured

## Limitations

- API shape/rate limits can vary; app fails gracefully and supports manual entry.
- Outputs are drafts and require qualified Hydrex review.

## Git workflow

```bash
git checkout -b feature/hud-workflow
git add .
git commit -m "Add HUD worksheet intelligence, assessed tank workflow, and branded exports"
git push -u origin feature/hud-workflow
```

## Troubleshooting

```bash
python3 -m py_compile app.py
grep -R -n --exclude-dir=.venv --exclude-dir=.git -E '^(<{7}|={7}|>{7})' .
sudo systemctl restart hydrex-form-assistant
journalctl -u hydrex-form-assistant -f
```
