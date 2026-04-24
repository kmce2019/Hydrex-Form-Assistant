from __future__ import annotations

import csv
import io
import json
import math
import os
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

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
    "latitude",
    "longitude",
    "buffer_half_mile_json",
    "buffer_one_mile_json",
    "environmental_results_json",
    "source_tracking_json",
]


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def migrate_table(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(projects)").fetchall()}
    desired = {
        "latitude": "REAL",
        "longitude": "REAL",
        "buffer_half_mile_json": "TEXT",
        "buffer_one_mile_json": "TEXT",
        "environmental_results_json": "TEXT",
        "source_tracking_json": "TEXT",
    }
    for column, dtype in desired.items():
        if column not in columns:
            conn.execute(f"ALTER TABLE projects ADD COLUMN {column} {dtype}")


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
                latitude REAL,
                longitude REAL,
                buffer_half_mile_json TEXT,
                buffer_one_mile_json TEXT,
                environmental_results_json TEXT,
                source_tracking_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        migrate_table(conn)


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


def float_or_none(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_json_load(raw: Any, default: Any) -> Any:
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def build_buffer(lat: float, lon: float, miles: float) -> dict[str, Any]:
    return {
        "type": "circle",
        "center": {"lat": lat, "lon": lon},
        "radius_miles": miles,
        "radius_meters": miles * 1609.344,
    }


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return radius * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def geocode_address(project: dict[str, Any]) -> dict[str, Any]:
    query = ", ".join(
        [
            value_or_unknown(project.get("address")),
            value_or_unknown(project.get("city")),
            value_or_unknown(project.get("state")),
        ]
    )
    params = urlencode({"q": query, "format": "json", "limit": 1})
    req = Request(
        f"https://nominatim.openstreetmap.org/search?{params}",
        headers={"User-Agent": "HydrexFormAssistant/1.0 (internal)"},
    )
    try:
        with urlopen(req, timeout=10) as response:
            body = json.loads(response.read().decode("utf-8"))
            if not body:
                return {"success": False, "error": "No geocoding match returned."}
            return {
                "success": True,
                "latitude": float(body[0]["lat"]),
                "longitude": float(body[0]["lon"]),
                "display_name": body[0].get("display_name", query),
            }
    except (URLError, HTTPError, TimeoutError, ValueError) as exc:
        return {"success": False, "error": f"Geocoding failed: {exc}"}


def query_epa_echo(lat: float, lon: float, radius_miles: float) -> dict[str, Any]:
    params = urlencode(
        {
            "p_lat": lat,
            "p_long": lon,
            "p_dist": radius_miles,
            "output": "JSON",
        }
    )
    req = Request(
        f"https://echo.epa.gov/tools/data-downloads/frs-facility-search?{params}",
        headers={"User-Agent": "HydrexFormAssistant/1.0 (internal)"},
    )

    try:
        with urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, HTTPError, TimeoutError, ValueError) as exc:
        return {
            "success": False,
            "error": f"EPA ECHO request failed: {exc}",
            "rcra_count": 0,
            "nearest_miles": None,
            "facilities": [],
        }

    facilities: list[dict[str, Any]] = []
    # Accommodate varying ECHO response shapes.
    rows = []
    if isinstance(payload, dict):
        rows = payload.get("Results", []) or payload.get("results", []) or payload.get("facilities", [])
    for item in rows[:50]:
        name = item.get("FacName") or item.get("fac_name") or item.get("FacilityName") or "Unnamed facility"
        lat2 = float_or_none(item.get("FacLat") or item.get("fac_lat") or item.get("Latitude"))
        lon2 = float_or_none(item.get("FacLong") or item.get("fac_long") or item.get("Longitude"))
        miles = None
        if lat2 is not None and lon2 is not None:
            miles = round(haversine_miles(lat, lon, lat2, lon2), 3)
        facilities.append(
            {
                "name": name,
                "type": item.get("FacTypeDesc") or item.get("fac_type") or "Unknown",
                "status": item.get("CAAComplianceStatus") or item.get("comp_status") or "Unknown",
                "distance_miles": miles,
                "latitude": lat2,
                "longitude": lon2,
            }
        )

    rcra_facilities = [f for f in facilities if "rcra" in f["type"].lower() or "haz" in f["type"].lower()]
    nearest = min((f["distance_miles"] for f in facilities if f["distance_miles"] is not None), default=None)

    return {
        "success": True,
        "rcra_count": len(rcra_facilities),
        "nearest_miles": nearest,
        "facilities": facilities,
    }


def parse_tceq_rows(raw_csv: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(raw_csv))
    rows = []
    for row in reader:
        rows.append(
            {
                "name": row.get("name") or row.get("facility_name") or row.get("site") or "Unnamed",
                "type": (row.get("type") or row.get("program") or "Unknown").upper(),
                "status": row.get("status") or "Unknown",
                "latitude": float_or_none(row.get("latitude") or row.get("lat")),
                "longitude": float_or_none(row.get("longitude") or row.get("lon") or row.get("lng")),
            }
        )
    return rows


def filter_tceq_results(lat: float, lon: float, rows: list[dict[str, Any]]) -> dict[str, Any]:
    filtered = []
    for row in rows:
        lat2, lon2 = row.get("latitude"), row.get("longitude")
        if lat2 is None or lon2 is None:
            continue
        dist = haversine_miles(lat, lon, lat2, lon2)
        row["distance_miles"] = round(dist, 3)
        if dist <= 1.0:
            filtered.append(row)

    lpst = [r for r in filtered if "LPST" in r["type"] and r["distance_miles"] <= 0.5]
    pst = [r for r in filtered if "PST" in r["type"] and r["distance_miles"] <= 1.0]

    nearest = min((r["distance_miles"] for r in filtered), default=None)
    return {
        "lpst_count": len(lpst),
        "pst_count": len(pst),
        "nearest_miles": nearest,
        "sites": filtered,
    }


def build_source_tracking(selected: list[str]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    status = {source: {"checked": source in selected, "timestamp": now if source in selected else None} for source in ["EPA ECHO", "NEPAssist", "TCEQ", "Site visit"]}
    return status


def run_environmental_search(project: dict[str, Any], tceq_csv: str | None, selected_sources: list[str]) -> dict[str, Any]:
    lat = float_or_none(project.get("latitude"))
    lon = float_or_none(project.get("longitude"))
    geocode_details = None

    if lat is None or lon is None:
        geocode = geocode_address(project)
        if not geocode.get("success"):
            return {
                "success": False,
                "error": geocode.get("error", "Geocoding failed."),
                "source_tracking": build_source_tracking(selected_sources),
            }
        lat = geocode["latitude"]
        lon = geocode["longitude"]
        geocode_details = geocode

    half_buffer = build_buffer(lat, lon, 0.5)
    one_buffer = build_buffer(lat, lon, 1.0)

    epa = query_epa_echo(lat, lon, 0.5)

    tceq_results = {"lpst_count": 0, "pst_count": 0, "nearest_miles": None, "sites": []}
    if tceq_csv:
        try:
            tceq_rows = parse_tceq_rows(tceq_csv)
            tceq_results = filter_tceq_results(lat, lon, tceq_rows)
        except Exception as exc:  # noqa: BLE001
            tceq_results = {"lpst_count": 0, "pst_count": 0, "nearest_miles": None, "sites": [], "error": str(exc)}

    nearest = [v for v in [epa.get("nearest_miles"), tceq_results.get("nearest_miles")] if isinstance(v, (int, float))]
    nearest_facility = min(nearest) if nearest else None

    results = {
        "success": True,
        "latitude": lat,
        "longitude": lon,
        "geocode": geocode_details,
        "buffers": {"half_mile": half_buffer, "one_mile": one_buffer},
        "rcra_count_half_mile": epa.get("rcra_count", 0),
        "lpst_count_half_mile": tceq_results.get("lpst_count", 0),
        "pst_count_one_mile": tceq_results.get("pst_count", 0),
        "nearest_facility_miles": nearest_facility,
        "epa_facilities": epa.get("facilities", []),
        "tceq_sites": tceq_results.get("sites", []),
        "sources_used": selected_sources,
        "source_tracking": build_source_tracking(selected_sources),
        "evidence_checklist": [
            {"item": "Map showing project + buffers", "present": bool(project.get("uploaded_refs"))},
            {"item": "EPA database search results", "present": "EPA ECHO" in selected_sources},
            {"item": "TCEQ database results", "present": "TCEQ" in selected_sources},
            {"item": "Site visit documentation", "present": "Site visit" in selected_sources},
            {"item": "Supporting reports", "present": bool(project.get("uploaded_refs"))},
        ],
    }

    return results


def generate_explosives_summary(project: dict[str, Any]) -> str:
    results = safe_json_load(project.get("environmental_results_json"), {})
    density = value_or_unknown(project.get("density_or_conversion"))
    tanks = value_or_unknown(project.get("nearby_tanks_notes"))
    pst_count = int_or_zero(results.get("pst_count_one_mile", project.get("pst_count")))
    nearest = results.get("nearest_facility_miles")
    nearest_phrase = f"Nearest mapped facility is approximately {nearest:.2f} miles away." if isinstance(nearest, (float, int)) else "Nearest mapped facility distance is not documented."

    return (
        f"Explosive and Flammable Hazards draft summary: The project screening indicates residential-density/conversion relevance: {density}. "
        f"Stationary aboveground tank review notes: {tanks}. Database/map-assisted review identified {pst_count} PST-related sites within one mile. "
        f"{nearest_phrase} Hydrex staff must verify separation distances, map evidence, and final hazard conclusions before submission."
    )


def generate_contamination_summary(project: dict[str, Any]) -> str:
    results = safe_json_load(project.get("environmental_results_json"), {})
    sources = ", ".join(results.get("sources_used", [])) or value_or_unknown(project.get("data_sources_checked"))
    rcra = int_or_zero(results.get("rcra_count_half_mile", project.get("rcra_count")))
    lpst = int_or_zero(results.get("lpst_count_half_mile", project.get("lpst_count")))
    nearest = results.get("nearest_facility_miles")
    nearest_phrase = f"Nearest identified facility was approximately {nearest:.2f} miles from the project." if isinstance(nearest, (float, int)) else "Nearest identified facility distance was not available."

    if rcra == 0 and lpst == 0:
        finding = "No hazardous or toxic substances were identified within the search radius based on database review."
    else:
        finding = "One or more facilities were identified; Hydrex staff should review site-specific details and confirm whether mitigation is needed."

    return (
        "Contamination and Toxic Substances draft summary: "
        f"EPA/TCEQ-style database and source review considered: {sources}. "
        f"The search identified {rcra} RCRA sites and {lpst} LPST sites within 0.5 mile. {nearest_phrase} {finding} "
        "This generated text is draft support and requires qualified Hydrex environmental review."
    )


def missing_evidence(project: dict[str, Any]) -> list[str]:
    checklist: list[str] = []
    results = safe_json_load(project.get("environmental_results_json"), {})

    if not project.get("uploaded_refs"):
        checklist.append("Map showing project point plus 0.5-mile and 1-mile buffers")
    if "EPA ECHO" not in results.get("sources_used", []):
        checklist.append("EPA database search results")
    if "TCEQ" not in results.get("sources_used", []):
        checklist.append("TCEQ database results")
    if "Site visit" not in results.get("sources_used", []):
        checklist.append("Site visit documentation")
    if value_or_unknown(project.get("description_of_work")) == "not documented":
        checklist.append("Description of work and supporting reports")

    return checklist


def build_markdown_report(project: dict[str, Any]) -> str:
    explosive = generate_explosives_summary(project)
    contamination = generate_contamination_summary(project)
    checklist = missing_evidence(project)
    results = safe_json_load(project.get("environmental_results_json"), {})

    lines = [
        f"# Hydrex Form Assistant Report - {value_or_unknown(project.get('project_name'))}",
        "",
        "## Project Intake",
    ]
    for field in FIELDS:
        if field.endswith("_json"):
            continue
        label = field.replace("_", " ").title()
        lines.append(f"- **{label}:** {value_or_unknown(project.get(field))}")

    lines.extend(
        [
            "",
            "## Automated Data Results",
            f"- **RCRA sites within 0.5 mile:** {int_or_zero(results.get('rcra_count_half_mile'))}",
            f"- **LPST sites within 0.5 mile:** {int_or_zero(results.get('lpst_count_half_mile'))}",
            f"- **PST sites within 1 mile:** {int_or_zero(results.get('pst_count_one_mile'))}",
            f"- **Nearest facility distance:** {results.get('nearest_facility_miles', 'not documented')}",
            f"- **Sources used:** {', '.join(results.get('sources_used', [])) or 'not documented'}",
            "",
            "## Explosive and Flammable Hazards (Draft)",
            explosive,
            "",
            "## Contamination and Toxic Substances (Draft)",
            contamination,
            "",
            "## Evidence Checklist",
        ]
    )

    lines.extend([f"- [ ] {item}" for item in checklist])

    lines.extend(
        [
            "",
            "---",
            "**Disclaimer:** This tool assists with data gathering and draft language generation only. "
            "All environmental determinations must be reviewed and approved by qualified Hydrex Environmental staff.",
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
            "SELECT id, project_name, client, city, state, latitude, longitude, updated_at FROM projects ORDER BY updated_at DESC"
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
    data["latitude"] = float_or_none(data.get("latitude"))
    data["longitude"] = float_or_none(data.get("longitude"))

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


@app.route("/api/environmental-search", methods=["POST"])
def environmental_search():
    payload = request.get_json(force=True) or {}
    project = payload.get("project", {})
    tceq_csv = payload.get("tceq_csv")
    selected_sources = payload.get("selected_sources", [])

    results = run_environmental_search(project, tceq_csv, selected_sources)
    if not results.get("success"):
        return jsonify(results), 400

    return jsonify(results)


@app.route("/api/generate", methods=["POST"])
def generate_outputs():
    project = request.get_json(force=True) or {}
    return jsonify(
        {
            "explosive_summary": generate_explosives_summary(project),
            "contamination_summary": generate_contamination_summary(project),
            "missing_evidence": missing_evidence(project),
            "disclaimer": (
                "This tool assists with data gathering and draft language generation only. "
                "All environmental determinations must be reviewed and approved by qualified Hydrex Environmental staff."
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
    port = int(os.environ.get("PORT", "8080"))
    host = os.environ.get("HOST", "0.0.0.0")
    app.run(debug=True, host=host, port=port)
