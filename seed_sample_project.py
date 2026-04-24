from app import FIELDS, get_connection, init_db


def main() -> None:
    init_db()
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
        "contamination_sources_notes": "Former dry cleaner listed 0.3 miles west; no other obvious sources noted in initial map review.",
        "rcra_count": 1,
        "lpst_count": 2,
        "pst_count": 3,
        "groundwater_notes": "County GIS layer indicates a historic plume area 0.6 miles south; outside 0.5-mile review buffer.",
        "radon_notes": "County classified Zone 2; recommend short-term radon testing before closeout.",
        "data_sources_checked": "EPA Envirofacts, state tank database, county GIS contamination overlays, aerial map buffer analysis.",
        "uploaded_refs": "Enviro map export 2026-04-14; Tank search PDF 2026-04-14; Site photos 2026-04-15.",
    }

    with get_connection() as conn:
        columns = ", ".join(FIELDS)
        placeholders = ", ".join(["?"] * len(FIELDS))
        values = [sample[field] for field in FIELDS]
        conn.execute(f"INSERT INTO projects ({columns}) VALUES ({placeholders})", values)
        conn.commit()

    print("Seeded sample project: Maple Court Rehab")


if __name__ == "__main__":
    main()
