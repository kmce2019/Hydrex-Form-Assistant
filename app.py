from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_file

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "hydrex_form_assistant.db"

app = Flask(__name__)

FIELDS = [
    "project_name",
    "client",
    "address",
    "city",
    "county",
    "state",
    "project_type",
    "site_visit_date",
    "inspector",
    "description_of_work",
    "density_or_conversion",
    "nearby_tanks_notes",
    "contamination_sources_notes",
    "rcra_count",
    "lpst_count",
    "pst_count",
    "groundwater_notes",
    "radon_notes",
    "data_sources_checked",
    "uploaded_refs",
]


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                client TEXT,
                address TEXT,
                city TEXT,
                county TEXT,
                state TEXT,
                project_type TEXT,
                site_visit_date TEXT,
                inspector TEXT,
                description_of_work TEXT,
                density_or_conversion TEXT,
                nearby_tanks_notes TEXT,
                contamination_sources_notes TEXT,
                rcra_count INTEGER DEFAULT 0,
                lpst_count INTEGER DEFAULT 0,
                pst_count INTEGER DEFAULT 0,
                groundwater_notes TEXT,
                radon_notes TEXT,
                data_sources_checked TEXT,
                uploaded_refs TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def value_or_unknown(value: str | None) -> str:
    if value is None or str(value).strip() == "":
        return "not documented"
    return str(value).strip()


def int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def generate_explosives_summary(project: dict[str, Any]) -> str:
    density = value_or_unknown(project.get("density_or_conversion"))
    tanks = value_or_unknown(project.get("nearby_tanks_notes"))
    project_type = value_or_unknown(project.get("project_type"))
    work = value_or_unknown(project.get("description_of_work"))

    return (
        f"Explosive and Flammable Hazards draft summary: The {value_or_unknown(project.get('project_name'))} "
        f"project is identified as {project_type}. The proposed activity is described as: {work}. "
        f"Project screening indicates whether development, construction, rehabilitation increasing residential "
        f"density, or conversion applies: {density}. Available documentation on stationary aboveground storage "
        f"tanks within one mile states: {tanks}. Based on these records, Hydrex staff should verify map "
        f"support, confirm any hazards requiring separation-distance analysis, and finalize worksheet conclusions."
    )


def generate_contamination_summary(project: dict[str, Any]) -> str:
    sources = value_or_unknown(project.get("contamination_sources_notes"))
    groundwater = value_or_unknown(project.get("groundwater_notes"))
    radon = value_or_unknown(project.get("radon_notes"))
    rcra = int_or_zero(project.get("rcra_count"))
    lpst = int_or_zero(project.get("lpst_count"))
    pst = int_or_zero(project.get("pst_count"))
    data_sources = value_or_unknown(project.get("data_sources_checked"))

    return (
        "Contamination and Toxic Substances draft summary: Site review considered available environmental "
        f"sources and map layers ({data_sources}). Notes on contamination sources within 0.5 mile: {sources}. "
        f"Mapped database counts include RCRA sites: {rcra}, LPST sites: {lpst}, and PST sites: {pst}. "
        f"Groundwater contamination review notes: {groundwater}. Radon exemption/testing status notes: {radon}. "
        "Hydrex staff should confirm whether toxic, hazardous, or radioactive substances are present, identify "
        "mitigation needs, and complete final worksheet determinations based on supporting evidence."
    )


def missing_evidence(project: dict[str, Any]) -> list[str]:
    checklist: list[str] = []

    required_text_fields = {
        "project_name": "Project name",
        "client": "Client",
        "address": "Address / location description",
        "city": "City",
        "county": "County",
        "state": "State",
        "project_type": "Project type",
        "site_visit_date": "Site visit date",
        "inspector": "Inspector/preparer",
        "description_of_work": "Description of work",
        "density_or_conversion": "Development/construction/rehab density/conversion determination",
        "nearby_tanks_notes": "Notes on nearby aboveground storage tanks within 1 mile",
        "contamination_sources_notes": "Notes on contamination sources within 0.5 mile",
        "groundwater_notes": "Groundwater contamination notes",
        "radon_notes": "Radon exemption/testing notes",
        "data_sources_checked": "Data sources checked",
        "uploaded_refs": "Uploaded map/report references",
    }

    for field, label in required_text_fields.items():
        if not value_or_unknown(project.get(field)) or value_or_unknown(project.get(field)) == "not documented":
            checklist.append(f"Provide {label}.")

    if int_or_zero(project.get("rcra_count")) == 0:
        checklist.append("Verify and document whether RCRA sites count is truly zero or not yet researched.")
    if int_or_zero(project.get("lpst_count")) == 0:
        checklist.append("Verify and document whether LPST count is truly zero or not yet researched.")
    if int_or_zero(project.get("pst_count")) == 0:
        checklist.append("Verify and document whether PST count is truly zero or not yet researched.")

    return checklist


def build_markdown_report(project: dict[str, Any]) -> str:
    explosive = generate_explosives_summary(project)
    contamination = generate_contamination_summary(project)
    checklist = missing_evidence(project)

    lines = [
        f"# Hydrex Form Assistant Report - {value_or_unknown(project.get('project_name'))}",
        "",
        "## Project Intake",
    ]
    for field in FIELDS:
        label = field.replace("_", " ").title()
        lines.append(f"- **{label}:** {value_or_unknown(project.get(field))}")

    lines.extend(
        [
            "",
            "## Explosive and Flammable Hazards (Draft)",
            explosive,
            "",
            "## Contamination and Toxic Substances (Draft)",
            contamination,
            "",
            "## Missing Evidence Checklist",
        ]
    )

    if checklist:
        lines.extend([f"- [ ] {item}" for item in checklist])
    else:
        lines.append("- [ ] No obvious gaps detected from provided fields; complete final staff review.")

    lines.extend(
        [
            "",
            "---",
            "**Disclaimer:** This draft content does not make final environmental determinations. "
            "Generated language must be reviewed and finalized by qualified Hydrex staff before submission.",
        ]
    )

    return "\n".join(lines)


@app.route("/")
def index() -> str:
    return render_template("index.html", today=date.today().isoformat())


@app.route("/api/projects", methods=["GET"])
def list_projects():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, project_name, client, city, state, updated_at FROM projects ORDER BY updated_at DESC"
        ).fetchall()
    return jsonify([row_to_dict(row) for row in rows])


@app.route("/api/projects/<int:project_id>", methods=["GET"])
def get_project(project_id: int):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        return jsonify({"error": "Project not found"}), 404
    return jsonify(row_to_dict(row))


@app.route("/api/projects", methods=["POST"])
def upsert_project():
    payload = request.get_json(force=True) or {}
    data = {field: payload.get(field, "") for field in FIELDS}

    data["rcra_count"] = int_or_zero(data["rcra_count"])
    data["lpst_count"] = int_or_zero(data["lpst_count"])
    data["pst_count"] = int_or_zero(data["pst_count"])

    with get_connection() as conn:
        project_id = payload.get("id")
        if project_id:
            assignments = ", ".join([f"{field} = ?" for field in FIELDS])
            values = [data[field] for field in FIELDS]
            conn.execute(
                f"UPDATE projects SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (*values, project_id),
            )
            conn.commit()
            saved_id = project_id
        else:
            placeholders = ", ".join(["?"] * len(FIELDS))
            columns = ", ".join(FIELDS)
            values = [data[field] for field in FIELDS]
            cursor = conn.execute(
                f"INSERT INTO projects ({columns}) VALUES ({placeholders})",
                values,
            )
            conn.commit()
            saved_id = cursor.lastrowid

        row = conn.execute("SELECT * FROM projects WHERE id = ?", (saved_id,)).fetchone()

    return jsonify(row_to_dict(row))


@app.route("/api/generate", methods=["POST"])
def generate_outputs():
    project = request.get_json(force=True) or {}
    return jsonify(
        {
            "explosive_summary": generate_explosives_summary(project),
            "contamination_summary": generate_contamination_summary(project),
            "missing_evidence": missing_evidence(project),
            "disclaimer": (
                "This draft content does not make final environmental determinations. "
                "Generated language must be reviewed by qualified Hydrex staff before submission."
            ),
        }
    )


@app.route("/api/projects/<int:project_id>/export", methods=["GET"])
def export_markdown(project_id: int):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()

    if row is None:
        return jsonify({"error": "Project not found"}), 404

    report = build_markdown_report(row_to_dict(row))
    export_dir = BASE_DIR / "exports"
    export_dir.mkdir(exist_ok=True)
    filename = f"project_{project_id}_report.md"
    file_path = export_dir / filename
    file_path.write_text(report, encoding="utf-8")

    return send_file(file_path, as_attachment=True, download_name=filename, mimetype="text/markdown")


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="127.0.0.1", port=6000)
    app.run(debug=True, host="127.0.0.1", port=5000)
