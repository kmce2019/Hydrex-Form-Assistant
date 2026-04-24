# Hydrex Form Assistant

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

## Install

1. Ensure Python 3.10+ is installed.
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

Then open: <http://127.0.0.1:6000>
Then open: <http://127.0.0.1:5000>

## Seed a Sample Project

```bash
python3 seed_sample_project.py
```

A sample project named **Maple Court Rehab** will be inserted into the SQLite database.

## Data Storage

- SQLite file: `hydrex_form_assistant.db`
- Markdown exports: `exports/`

## Notes

This app does **not** make final environmental determinations. Generated text must be reviewed and finalized by qualified Hydrex staff before submission.
