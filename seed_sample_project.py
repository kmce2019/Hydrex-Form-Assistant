import json

from app import FIELDS, get_connection, init_db


def main() -> None:
    init_db()
    selected_tank = {
        "name": "Maple Fuel Depot",
        "type": "LPST",
        "status": "Investigating",
        "distance_miles": 0.28,
        "latitude": 31.109,
        "longitude": -97.742,
        "capacity": "5000",
        "contents": "Diesel",
        "registry_id": "TX-12345",
        "asd_status": "review required",
    }
    environmental_results = {
        "success": True,
        "latitude": 31.105,
        "longitude": -97.748,
        "rcra_count_half_mile": 1,
        "lpst_count_half_mile": 2,
        "pst_count_one_mile": 3,
        "nearest_facility_miles": 0.28,
        "sources_used": ["EPA ECHO", "TCEQ", "Site visit"],
        "source_tracking": {
            "EPA ECHO": {"checked": True, "timestamp": "2026-04-24T10:15:00Z"},
            "TCEQ": {"checked": True, "timestamp": "2026-04-24T10:16:00Z"},
            "Site visit": {"checked": True, "timestamp": "2026-04-24T11:00:00Z"},
            "NEPAssist": {"checked": False, "timestamp": None},
        },
        "evidence_checklist": [],
        "epa_facilities": [{"name": "Acme Hazard Storage", "type": "RCRA", "status": "Unknown", "distance_miles": 0.42}],
        "tceq_sites": [selected_tank],
    }

    sample = {
        "project_name": "Maple Court Rehab",
        "client": "Hydrex Housing Partners",
        "address": "1250 Maple Court, near intersection of Pine St and 4th Ave",
        "city": "Dayton",
        "county": "Montgomery",
        "state": "OH",
        "project_type": "Multifamily rehabilitation",
        "site_visit_date": "2026-04-15",
        "inspector": "A. Rivera",
        "description_of_work": "Interior rehab with unit modernization; no footprint expansion.",
        "density_or_conversion": "No",
        "nearby_tanks_notes": "One aboveground diesel AST identified approximately 0.8 miles southeast; confirm capacity and ownership.",
        "contamination_sources_notes": "Former dry cleaner listed 0.3 miles west; one RCRA facility and two LPST sites require staff review.",
        "rcra_count": 1,
        "lpst_count": 2,
        "pst_count": 3,
        "groundwater_notes": "County GIS layer indicates historic plume area 0.6 miles south; outside 0.5-mile review buffer.",
        "radon_notes": "County classified Zone 2; recommend short-term radon testing before closeout.",
        "data_sources_checked": "EPA ECHO, TCEQ CSV dataset, Site visit notes, county GIS contamination overlays.",
        "uploaded_refs": "Map with 0.5/1 mile buffers, EPA export 2026-04-24, TCEQ dataset review memo.",
        "latitude": 31.105,
        "longitude": -97.748,
        "buffer_half_mile_json": json.dumps({"type": "circle", "center": {"lat": 31.105, "lon": -97.748}, "radius_miles": 0.5}),
        "buffer_one_mile_json": json.dumps({"type": "circle", "center": {"lat": 31.105, "lon": -97.748}, "radius_miles": 1.0}),
        "environmental_results_json": json.dumps(environmental_results),
        "source_tracking_json": json.dumps(environmental_results["source_tracking"]),
        "selected_tank_json": json.dumps(selected_tank),
    }

    with get_connection() as conn:
        columns = ", ".join(FIELDS)
        placeholders = ", ".join(["?"] * len(FIELDS))
        values = [sample.get(field, "") for field in FIELDS]
        conn.execute(f"INSERT INTO projects ({columns}) VALUES ({placeholders})", values)
        conn.commit()

    print("Seeded sample project with HUD answer workflow data: Maple Court Rehab")


if __name__ == "__main__":
    main()
