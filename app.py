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

EPA_ECHO_ENABLED = os.environ.get("EPA_ECHO_ENABLED", "true").lower() != "false"
TCEQ_ARCGIS_LAYER_URL = os.environ.get("TCEQ_ARCGIS_LAYER_URL", "").strip()
DEFAULT_PORT = int(os.environ.get("DEFAULT_PORT", "8080"))

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
    "selected_tank_json",
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
        "selected_tank_json": "TEXT",
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
                selected_tank_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        migrate_table(conn)


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def value_or_unknown(value: Any) -> str:
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


def json_dumps_compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


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
        with urlopen(req, timeout=12) as response:
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
    if not EPA_ECHO_ENABLED:
        return {"success": True, "rcra_count": 0, "nearest_miles": None, "facilities": [], "disabled": True}

    params = urlencode({"p_lat": lat, "p_long": lon, "p_dist": radius_miles, "output": "JSON"})
    req = Request(
        f"https://echo.epa.gov/tools/data-downloads/frs-facility-search?{params}",
        headers={"User-Agent": "HydrexFormAssistant/1.0 (internal)"},
    )
    try:
        with urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, HTTPError, TimeoutError, ValueError) as exc:
        return {"success": False, "error": f"EPA ECHO request failed: {exc}", "rcra_count": 0, "nearest_miles": None, "facilities": []}

    rows = []
    if isinstance(payload, dict):
        rows = payload.get("Results", []) or payload.get("results", []) or payload.get("facilities", [])

    facilities: list[dict[str, Any]] = []
    for item in rows[:80]:
        name = item.get("FacName") or item.get("fac_name") or item.get("FacilityName") or "Unnamed facility"
        lat2 = float_or_none(item.get("FacLat") or item.get("fac_lat") or item.get("Latitude"))
        lon2 = float_or_none(item.get("FacLong") or item.get("fac_long") or item.get("Longitude"))
        distance = None
        if lat2 is not None and lon2 is not None:
            distance = round(haversine_miles(lat, lon, lat2, lon2), 3)
        facilities.append(
            {
                "name": name,
                "type": item.get("FacTypeDesc") or item.get("fac_type") or "Unknown",
                "status": item.get("CAAComplianceStatus") or item.get("comp_status") or "Unknown",
                "latitude": lat2,
                "longitude": lon2,
                "distance_miles": distance,
                "source": "EPA ECHO",
            }
        )

    rcra = [f for f in facilities if "rcra" in f["type"].lower() or "haz" in f["type"].lower()]
    nearest = min((f["distance_miles"] for f in facilities if f.get("distance_miles") is not None), default=None)
    return {"success": True, "rcra_count": len(rcra), "nearest_miles": nearest, "facilities": facilities}


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
                "capacity": row.get("capacity") or "",
                "contents": row.get("contents") or "",
                "registry_id": row.get("registry_id") or row.get("id") or "",
                "source": "TCEQ CSV",
            }
        )
    return rows


def query_tceq_arcgis(lat: float, lon: float) -> list[dict[str, Any]]:
    if not TCEQ_ARCGIS_LAYER_URL:
        return []
    # Optional hook: fetch ArcGIS JSON if configured.
    try:
        params = urlencode({"f": "json", "where": "1=1", "outFields": "*", "resultRecordCount": 200})
        req = Request(f"{TCEQ_ARCGIS_LAYER_URL.rstrip('/')}/query?{params}", headers={"User-Agent": "HydrexFormAssistant/1.0"})
        with urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []

    normalized: list[dict[str, Any]] = []
    for feature in payload.get("features", []):
        attrs = feature.get("attributes", {})
        geom = feature.get("geometry", {})
        lat2 = float_or_none(geom.get("y") or attrs.get("latitude") or attrs.get("LATITUDE"))
        lon2 = float_or_none(geom.get("x") or attrs.get("longitude") or attrs.get("LONGITUDE"))
        if lat2 is None or lon2 is None:
            continue
        normalized.append(
            {
                "name": attrs.get("name") or attrs.get("facility_name") or "Unnamed",
                "type": str(attrs.get("type") or attrs.get("program") or "PST"),
                "status": str(attrs.get("status") or "Unknown"),
                "latitude": lat2,
                "longitude": lon2,
                "capacity": str(attrs.get("capacity") or ""),
                "contents": str(attrs.get("contents") or ""),
                "registry_id": str(attrs.get("registry_id") or attrs.get("id") or ""),
                "source": "TCEQ ArcGIS",
            }
        )
    return normalized


def normalize_tceq_results(lat: float, lon: float, rows: list[dict[str, Any]]) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        lat2, lon2 = row.get("latitude"), row.get("longitude")
        if lat2 is None or lon2 is None:
            continue
        dist = round(haversine_miles(lat, lon, lat2, lon2), 3)
        normalized.append({
            "name": row.get("name") or "Unnamed",
            "type": str(row.get("type") or "Unknown").upper(),
            "status": row.get("status") or "Unknown",
            "latitude": lat2,
            "longitude": lon2,
            "distance_miles": dist,
            "source": row.get("source") or "TCEQ",
            "capacity": row.get("capacity") or "",
            "contents": row.get("contents") or "",
            "registry_id": row.get("registry_id") or "",
        })

    within_half = [r for r in normalized if r["distance_miles"] <= 0.5]
    within_one = [r for r in normalized if r["distance_miles"] <= 1.0]
    lpst_half = [r for r in within_half if "LPST" in r["type"]]
    pst_one = [r for r in within_one if "PST" in r["type"] or "TANK" in r["type"]]

    nearest = min((r["distance_miles"] for r in within_one), default=None)
    return {
        "sites": within_one,
        "lpst_count_half_mile": len(lpst_half),
        "pst_count_one_mile": len(pst_one),
        "nearest_miles": nearest,
    }


def build_source_tracking(selected: list[str]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    all_sources = ["EPA ECHO", "NEPAssist", "TCEQ", "Site visit"]
    return {src: {"checked": src in selected, "timestamp": now if src in selected else None} for src in all_sources}


def run_environmental_search(project: dict[str, Any], tceq_csv: str | None, selected_sources: list[str]) -> dict[str, Any]:
    lat = float_or_none(project.get("latitude"))
    lon = float_or_none(project.get("longitude"))
    geocode_info = None

    if lat is None or lon is None:
        geocode = geocode_address(project)
        if not geocode.get("success"):
            return {"success": False, "error": geocode.get("error", "Geocoding failed."), "source_tracking": build_source_tracking(selected_sources)}
        lat, lon = geocode["latitude"], geocode["longitude"]
        geocode_info = geocode

    half_buffer = build_buffer(lat, lon, 0.5)
    one_buffer = build_buffer(lat, lon, 1.0)

    epa = query_epa_echo(lat, lon, 0.5)
    tceq_rows = []
    if tceq_csv:
        tceq_rows.extend(parse_tceq_rows(tceq_csv))
    tceq_rows.extend(query_tceq_arcgis(lat, lon))
    tceq = normalize_tceq_results(lat, lon, tceq_rows)

    nearest_pool = [v for v in [epa.get("nearest_miles"), tceq.get("nearest_miles")] if isinstance(v, (float, int))]
    nearest = min(nearest_pool) if nearest_pool else None

    rcra_count = epa.get("rcra_count", 0)
    lpst_count = tceq.get("lpst_count_half_mile", 0)
    pst_count = tceq.get("pst_count_one_mile", 0)

    results = {
        "success": True,
        "latitude": lat,
        "longitude": lon,
        "geocode": geocode_info,
        "buffers": {"half_mile": half_buffer, "one_mile": one_buffer},
        "rcra_count_half_mile": rcra_count,
        "lpst_count_half_mile": lpst_count,
        "pst_count_one_mile": pst_count,
        "nearest_facility_miles": nearest,
        "epa_facilities": epa.get("facilities", []),
        "tceq_sites": tceq.get("sites", []),
        "sources_used": selected_sources,
        "source_tracking": build_source_tracking(selected_sources),
        "errors": [epa.get("error")] if epa.get("error") else [],
    }

    results["evidence_checklist"] = build_evidence_checklist(project, results, safe_json_load(project.get("selected_tank_json"), {}))
    return results


def pick_primary_tank(results: dict[str, Any]) -> dict[str, Any] | None:
    tanks = [s for s in results.get("tceq_sites", []) if "PST" in s.get("type", "") or "TANK" in s.get("type", "")]
    if not tanks:
        return None
    return sorted(tanks, key=lambda x: x.get("distance_miles") or 999)[0]


def smart_hud_answers(project: dict[str, Any]) -> dict[str, Any]:
    results = safe_json_load(project.get("environmental_results_json"), {})
    selected_tank = safe_json_load(project.get("selected_tank_json"), {})

    density = value_or_unknown(project.get("density_or_conversion")).lower()
    density_ans = "yes" if density == "yes" else "no" if density == "no" else "unknown"

    pst_count = int_or_zero(results.get("pst_count_one_mile", project.get("pst_count")))
    tanks_within_one = "yes" if pst_count > 0 else "no"
    hazardous_included = "unknown"
    if "hazardous" in value_or_unknown(project.get("project_type")).lower():
        hazardous_included = "yes"

    asd = "not applicable"
    acceptable_distance = "not applicable"
    mitigation = "unknown"
    if tanks_within_one == "yes":
        asd = "unknown"
        acceptable_distance = "unknown"
        mitigation = "unknown"
        if selected_tank:
            dist = float_or_none(selected_tank.get("distance_miles"))
            if dist is not None and dist > 0.75:
                asd = "yes"
                acceptable_distance = "yes"
                mitigation = "no"
            elif dist is not None:
                asd = "unknown"
                acceptable_distance = "unknown"
                mitigation = "yes"
    else:
        mitigation = "no"

    rcra = int_or_zero(results.get("rcra_count_half_mile", project.get("rcra_count")))
    lpst = int_or_zero(results.get("lpst_count_half_mile", project.get("lpst_count")))
    pst = int_or_zero(results.get("pst_count_one_mile", project.get("pst_count")))
    contamination_notes = value_or_unknown(project.get("contamination_sources_notes"))

    toxic_found = "no"
    if rcra > 0 or lpst > 0 or pst > 0 or contamination_notes != "not documented":
        toxic_found = "yes"

    radon_notes = value_or_unknown(project.get("radon_notes")).lower()
    radon_status = "unknown"
    if "exempt" in radon_notes:
        radon_status = "exempt"
    elif "test" in radon_notes:
        radon_status = "tested"
    elif "review" in radon_notes or "zone" in radon_notes:
        radon_status = "data review"

    contamination_mitigation = "yes" if toxic_found == "yes" else "no"
    compliance_status = "unknown"
    if toxic_found == "no":
        compliance_status = "compliant"
    elif contamination_mitigation == "yes":
        compliance_status = "review required"
        if value_or_unknown(project.get("groundwater_notes")) != "not documented":
            compliance_status = "mitigation required"

    return {
        "explosive_and_flammable_hazards": {
            "q1_hazardous_facility_included": hazardous_included,
            "q2_density_or_conversion": density_ans,
            "q3_aboveground_storage_within_1_mile": tanks_within_one,
            "q4_asd_acceptable": asd,
            "q5_acceptable_distance": acceptable_distance,
            "q6_mitigation_needed": mitigation,
        },
        "contamination_and_toxic_substances": {
            "evaluation_method_used": value_or_unknown(project.get("data_sources_checked")),
            "toxic_substances_found": toxic_found,
            "radon_status": radon_status,
            "mitigation_needed": contamination_mitigation,
            "compliance_status_draft": compliance_status,
        },
    }


def generate_explosives_summary(project: dict[str, Any], hud_answers: dict[str, Any]) -> str:
    results = safe_json_load(project.get("environmental_results_json"), {})
    selected_tank = safe_json_load(project.get("selected_tank_json"), {})

    q = hud_answers["explosive_and_flammable_hazards"]
    pst = int_or_zero(results.get("pst_count_one_mile", project.get("pst_count")))

    if pst == 0 and q["q2_density_or_conversion"] == "no":
        return (
            "Explosive and Flammable Hazards draft summary: No aboveground storage tank/PST sources were identified within one mile "
            "and project activity does not indicate a residential density increase/conversion trigger based on provided information. "
            "This supports a preliminary compliance posture, subject to Hydrex staff verification and final worksheet completion."
        )

    base = (
        f"Explosive and Flammable Hazards draft summary: Project activity density/conversion response is {q['q2_density_or_conversion']}. "
        f"Database/map review identified {pst} tank/PST records within one mile. ASD verification is required where applicable. "
    )

    if selected_tank:
        base += (
            f"Selected assessed tank: {selected_tank.get('name', 'Unnamed')} ({selected_tank.get('type', 'type unknown')}), "
            f"distance {selected_tank.get('distance_miles', 'unknown')} miles, contents {selected_tank.get('contents') or 'not documented'}, "
            f"capacity {selected_tank.get('capacity') or 'not documented'}. "
            f"Draft ASD status: {q['q4_asd_acceptable']}. "
        )

    base += "Generated language is draft support only; qualified Hydrex staff must confirm final environmental determinations."
    return base


def generate_contamination_summary(project: dict[str, Any], hud_answers: dict[str, Any]) -> str:
    results = safe_json_load(project.get("environmental_results_json"), {})
    rcra = int_or_zero(results.get("rcra_count_half_mile", project.get("rcra_count")))
    lpst = int_or_zero(results.get("lpst_count_half_mile", project.get("lpst_count")))
    pst = int_or_zero(results.get("pst_count_one_mile", project.get("pst_count")))

    site_visit_date = value_or_unknown(project.get("site_visit_date"))
    inspector = value_or_unknown(project.get("inspector"))
    sources = ", ".join(results.get("sources_used", [])) or value_or_unknown(project.get("data_sources_checked"))
    groundwater = value_or_unknown(project.get("groundwater_notes"))
    radon = value_or_unknown(project.get("radon_notes"))
    contamination_notes = value_or_unknown(project.get("contamination_sources_notes"))

    nearest = results.get("nearest_facility_miles")
    nearest_txt = f"Nearest mapped facility distance: {nearest} miles." if nearest is not None else "Nearest mapped facility distance not documented."

    if rcra == 0 and lpst == 0 and pst == 0 and contamination_notes == "not documented":
        return (
            f"Contamination and Toxic Substances draft summary: Database/map review ({sources}) and site visit context "
            f"(date {site_visit_date}, preparer {inspector}) did not identify known contamination sources within searched radii. "
            f"Groundwater notes: {groundwater}. Radon notes: {radon}. {nearest_txt} "
            "Draft support only; Hydrex staff review required before any final determination."
        )

    names = [s.get("name") for s in (results.get("epa_facilities", [])[:3] + results.get("tceq_sites", [])[:3]) if s.get("name")]
    name_txt = ", ".join(names) if names else "specific site names not captured"
    compliance = hud_answers["contamination_and_toxic_substances"]["compliance_status_draft"]

    return (
        f"Contamination and Toxic Substances draft summary: Review methods included {sources}; site visit date {site_visit_date} by {inspector}. "
        f"Identified counts: RCRA within 0.5 mile = {rcra}, LPST within 0.5 mile = {lpst}, PST/tanks within 1 mile = {pst}. "
        f"Nearby source names (sample): {name_txt}. {nearest_txt} Groundwater notes: {groundwater}. Radon notes: {radon}. "
        f"Draft compliance status: {compliance}. Hydrex staff must review and finalize mitigation/compliance conclusions."
    )


def build_evidence_checklist(project: dict[str, Any], results: dict[str, Any], selected_tank: dict[str, Any] | None) -> list[dict[str, Any]]:
    tanks_present = int_or_zero(results.get("pst_count_one_mile", project.get("pst_count"))) > 0
    checklist = [
        {"item": "Project location/address", "present": value_or_unknown(project.get("address")) != "not documented"},
        {"item": "Project map with 0.5-mile and 1-mile buffers", "present": bool(results.get("buffers"))},
        {"item": "EPA ECHO search results", "present": "EPA ECHO" in results.get("sources_used", [])},
        {"item": "TCEQ PST/LPST search results", "present": "TCEQ" in results.get("sources_used", [])},
        {"item": "NEPAssist/map screenshot", "present": "NEPAssist" in results.get("sources_used", []) or bool(project.get("uploaded_refs"))},
        {"item": "Site visit date/notes", "present": value_or_unknown(project.get("site_visit_date")) != "not documented" and "Site visit" in results.get("sources_used", [])},
        {"item": "Source tracking timestamps", "present": bool(results.get("source_tracking"))},
        {"item": "Selected assessed tank if tanks are present", "present": (not tanks_present) or bool(selected_tank)},
        {"item": "ASD calculation if assessed tank requires it", "present": (not tanks_present) or (bool(selected_tank) and selected_tank.get("asd_status"))},
        {"item": "Radon notes/testing/data review", "present": value_or_unknown(project.get("radon_notes")) != "not documented"},
        {"item": "Mitigation notes if applicable", "present": value_or_unknown(project.get("groundwater_notes")) != "not documented" or value_or_unknown(project.get("contamination_sources_notes")) != "not documented"},
    ]
    return checklist


def missing_evidence(project: dict[str, Any]) -> list[str]:
    results = safe_json_load(project.get("environmental_results_json"), {})
    selected_tank = safe_json_load(project.get("selected_tank_json"), {})
    checklist = build_evidence_checklist(project, results, selected_tank)
    return [item["item"] for item in checklist if not item["present"]]


def build_report_sections(project: dict[str, Any], hud_answers: dict[str, Any], explosive_summary: str, contamination_summary: str) -> dict[str, Any]:
    results = safe_json_load(project.get("environmental_results_json"), {})
    selected_tank = safe_json_load(project.get("selected_tank_json"), {})
    evidence = build_evidence_checklist(project, results, selected_tank)
    return {
        "project_information": {
            "project_name": value_or_unknown(project.get("project_name")),
            "client": value_or_unknown(project.get("client")),
            "location": ", ".join([value_or_unknown(project.get("address")), value_or_unknown(project.get("city")), value_or_unknown(project.get("state"))]),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "label": "Draft - Staff Review Required",
        },
        "source_tracking": results.get("source_tracking", {}),
        "environmental_results": {
            "rcra_0_5_mile": int_or_zero(results.get("rcra_count_half_mile")),
            "lpst_0_5_mile": int_or_zero(results.get("lpst_count_half_mile")),
            "pst_1_mile": int_or_zero(results.get("pst_count_one_mile")),
            "nearest_facility_miles": results.get("nearest_facility_miles"),
        },
        "explosive_section": explosive_summary,
        "contamination_section": contamination_summary,
        "hud_answers": hud_answers,
        "selected_tank": selected_tank,
        "evidence_checklist": evidence,
        "disclaimer": "This tool assists with data gathering and draft language generation only. All environmental determinations must be reviewed and approved by qualified Hydrex Environmental staff.",
    }


def build_markdown_report(project: dict[str, Any]) -> str:
    hud_answers = smart_hud_answers(project)
    explosive_summary = generate_explosives_summary(project, hud_answers)
    contamination_summary = generate_contamination_summary(project, hud_answers)
    sections = build_report_sections(project, hud_answers, explosive_summary, contamination_summary)

    lines: list[str] = [
        f"# Hydrex Form Assistant Report - {sections['project_information']['project_name']}",
        "",
        "## Draft - Staff Review Required",
        f"- **Client:** {sections['project_information']['client']}",
        f"- **Location:** {sections['project_information']['location']}",
        f"- **Generated:** {sections['project_information']['generated_at']}",
        "",
        "## Environmental Data Results",
        f"- **RCRA within 0.5 mile:** {sections['environmental_results']['rcra_0_5_mile']}",
        f"- **LPST within 0.5 mile:** {sections['environmental_results']['lpst_0_5_mile']}",
        f"- **PST/Tank within 1 mile:** {sections['environmental_results']['pst_1_mile']}",
        f"- **Nearest facility distance (mi):** {sections['environmental_results']['nearest_facility_miles']}",
        "",
        "## Explosive and Flammable Hazards (Draft)",
        explosive_summary,
        "",
        "## Contamination and Toxic Substances (Draft)",
        contamination_summary,
        "",
        "## HUD Answers",
        "```json",
        json.dumps(hud_answers, indent=2),
        "```",
        "",
        "## Selected Assessed Tank",
        f"```json\n{json.dumps(sections['selected_tank'], indent=2)}\n```",
        "",
        "## Evidence Checklist",
    ]

    for item in sections["evidence_checklist"]:
        lines.append(f"- [{'x' if item['present'] else ' '}] {item['item']}")

    lines.extend([
        "",
        "---",
        f"**Disclaimer:** {sections['disclaimer']}",
    ])

    return "\n".join(lines)


def build_pdf_report(project: dict[str, Any], out_path: Path) -> None:
    try:
        from reportlab.lib.pagesizes import LETTER
        from reportlab.pdfgen import canvas
    except Exception as exc:
        raise RuntimeError(f"reportlab unavailable: {exc}") from exc

    hud_answers = smart_hud_answers(project)
    explosive_summary = generate_explosives_summary(project, hud_answers)
    contamination_summary = generate_contamination_summary(project, hud_answers)
    sections = build_report_sections(project, hud_answers, explosive_summary, contamination_summary)

    c = canvas.Canvas(str(out_path), pagesize=LETTER)
    width, height = LETTER
    y = height - 40

    def line(text: str, size: int = 10, gap: int = 14):
        nonlocal y
        c.setFont("Helvetica", size)
        c.drawString(40, y, text[:130])
        y -= gap
        if y < 60:
            c.showPage()
            y = height - 40

    c.setTitle("Hydrex Environmental Report")
    line("Hydrex Form Assistant / Hydrex Environmental", 14, 20)
    line("Draft - Staff Review Required", 11, 18)
    line(f"Project: {sections['project_information']['project_name']}")
    line(f"Client: {sections['project_information']['client']}")
    line(f"Generated: {sections['project_information']['generated_at']}")
    line("")

    line("Environmental Data Results", 12, 18)
    er = sections["environmental_results"]
    line(f"RCRA 0.5 mile: {er['rcra_0_5_mile']}")
    line(f"LPST 0.5 mile: {er['lpst_0_5_mile']}")
    line(f"PST 1 mile: {er['pst_1_mile']}")
    line(f"Nearest facility miles: {er['nearest_facility_miles']}")

    line("")
    line("Explosive and Flammable Hazards (Draft)", 12, 18)
    for segment in explosive_summary.split(". "):
        line(segment)

    line("")
    line("Contamination and Toxic Substances (Draft)", 12, 18)
    for segment in contamination_summary.split(". "):
        line(segment)

    line("")
    line("HUD Answer Table", 12, 18)
    for section_name, answers in hud_answers.items():
        line(section_name, 11, 14)
        for k, v in answers.items():
            line(f"- {k}: {v}")

    line("")
    line("Selected Assessed Tank", 12, 18)
    selected_tank = sections.get("selected_tank") or {}
    if selected_tank:
        for k, v in selected_tank.items():
            line(f"- {k}: {v}")
    else:
        line("- none selected")

    line("")
    line("Evidence Checklist", 12, 18)
    for item in sections["evidence_checklist"]:
        line(f"[{'X' if item['present'] else ' '}] {item['item']}")

    line("")
    line(f"Disclaimer: {sections['disclaimer']}")

    c.showPage()
    c.save()


@app.route("/")
def index() -> str:
    return render_template("index.html", today=date.today().isoformat())


@app.route("/api/projects", methods=["GET"])
def list_projects():
    with get_connection() as conn:
        rows = conn.execute("SELECT id, project_name, client, city, state, latitude, longitude, updated_at FROM projects ORDER BY updated_at DESC").fetchall()
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
            conn.execute(f"UPDATE projects SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (*values, project_id))
            conn.commit()
            saved_id = project_id
        else:
            placeholders = ", ".join(["?"] * len(FIELDS))
            columns = ", ".join(FIELDS)
            values = [data[field] for field in FIELDS]
            cursor = conn.execute(f"INSERT INTO projects ({columns}) VALUES ({placeholders})", values)
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
    hud_answers = smart_hud_answers(project)
    explosive_summary = generate_explosives_summary(project, hud_answers)
    contamination_summary = generate_contamination_summary(project, hud_answers)
    report_sections = build_report_sections(project, hud_answers, explosive_summary, contamination_summary)

    return jsonify(
        {
            "explosive_summary": explosive_summary,
            "contamination_summary": contamination_summary,
            "hud_answers": hud_answers,
            "missing_evidence": [i["item"] for i in report_sections["evidence_checklist"] if not i["present"]],
            "report_sections": report_sections,
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


@app.route("/api/projects/<int:project_id>/export/pdf", methods=["GET"])
def export_pdf(project_id: int):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        return jsonify({"error": "Project not found"}), 404

    export_dir = BASE_DIR / "exports"
    export_dir.mkdir(exist_ok=True)
    filename = f"project_{project_id}_report.pdf"
    file_path = export_dir / filename
    try:
        build_pdf_report(row_to_dict(row), file_path)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 500

    return send_file(file_path, as_attachment=True, download_name=filename, mimetype="application/pdf")


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", str(DEFAULT_PORT)))
    host = os.environ.get("HOST", "0.0.0.0")
    app.run(debug=True, host=host, port=port)
