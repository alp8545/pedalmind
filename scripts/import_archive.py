"""Import activities from garmin-analyzer archivio_completo.json into PedalMind DB via API."""
import json
import sys
import time
import re
import requests

API_BASE = "https://pedalmind-production.up.railway.app"
ARCHIVE_PATH = "/home/alessio/garmin-analyzer/results/archivio_completo.json"


def extract_date_from_filename(filename: str) -> str | None:
    """Extract date from filename like '2026-03-22_road_biking_22260272063.fit'."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})", filename)
    return m.group(1) if m else None


def extract_garmin_id(filename: str) -> int | None:
    """Extract Garmin activity ID from filename."""
    m = re.search(r"_(\d{8,})\.fit", filename)
    return int(m.group(1)) if m else None


def convert_activity(act: dict) -> dict | None:
    """Convert garmin-analyzer format to PedalMind Activity fields."""
    filename = act.get("file", "")
    date_str = extract_date_from_filename(filename)
    garmin_id = extract_garmin_id(filename)
    if not garmin_id:
        return None

    # Build name from date + type
    sport = act.get("activity_type", "cycling")
    name = f"{date_str} {sport}" if date_str else sport

    # Duration
    duration_secs = act.get("elapsed_time_sec") or act.get("moving_time_sec")
    if not duration_secs and act.get("durata_min"):
        duration_secs = act["durata_min"] * 60

    # Distance
    distance_m = (act.get("distanza_km") or 0) * 1000

    # Power zones as dict for raw_data
    raw_data = {
        "source": "garmin-analyzer-import",
        "zone_potenza": act.get("zone_potenza"),
        "zone_potenza_sec": act.get("zone_potenza_sec"),
        "zone_fc": act.get("zone_fc"),
        "zone_fc_sec": act.get("zone_fc_sec"),
        "best_power": {
            "5s": act.get("best_5s"),
            "10s": act.get("best_10s"),
            "30s": act.get("best_30s"),
            "1min": act.get("best_1min"),
            "5min": act.get("best_5min"),
            "10min": act.get("best_10min"),
            "20min": act.get("best_20min"),
        },
        "variability_index": act.get("variability_index"),
        "decoupling_pct": act.get("decoupling_aerobico_%"),
        "temperatura_media": act.get("temperatura_media"),
    }

    # Convert laps to splits_data format
    laps = act.get("laps", [])
    splits_data = None
    if laps:
        lap_dtos = []
        for lap in laps:
            lap_dtos.append({
                "distance": (lap.get("distanza_km") or lap.get("dist_km") or 0) * 1000,
                "duration": lap.get("durata_sec") or (lap.get("dur_min", 0) * 60),
                "averagePower": lap.get("potenza_media") or lap.get("pot_media"),
                "maxPower": lap.get("potenza_max") or lap.get("pot_max"),
                "normalizedPower": lap.get("potenza_normalizzata"),
                "averageHR": lap.get("fc_media") or lap.get("fc"),
                "maxHR": lap.get("fc_max"),
                "averageBikeCadence": lap.get("cadenza_media") or lap.get("cadenza"),
                "averageSpeed": (lap.get("velocita_media_kmh") or lap.get("vel_media") or 0) / 3.6,
                "elevationGain": lap.get("dislivello_positivo") or lap.get("disliv_pos"),
                "elevationLoss": lap.get("dislivello_negativo") or lap.get("disliv_neg"),
            })
        splits_data = {"lapDTOs": lap_dtos}

    # Build analysis_text from available data
    analysis_parts = []
    if act.get("IF"):
        if act["IF"] < 0.75:
            analysis_parts.append(f"Tipo: Recupero attivo (IF {act['IF']:.2f})")
        elif act["IF"] < 0.85:
            analysis_parts.append(f"Tipo: Endurance (IF {act['IF']:.2f})")
        elif act["IF"] < 0.95:
            analysis_parts.append(f"Tipo: Tempo/Sweet Spot (IF {act['IF']:.2f})")
        elif act["IF"] <= 1.05:
            analysis_parts.append(f"Tipo: Threshold (IF {act['IF']:.2f})")
        else:
            analysis_parts.append(f"Tipo: VO2max/Race (IF {act['IF']:.2f})")

    if act.get("potenza_normalizzata"):
        analysis_parts.append(f"NP: {act['potenza_normalizzata']:.0f}W | TSS: {act.get('TSS', 0):.0f}")
    if act.get("w_kg"):
        analysis_parts.append(f"W/kg: {act['w_kg']:.2f} (NP: {act.get('w_kg_np', 0):.2f})")
    if act.get("decoupling_aerobico_%") is not None:
        dec = act["decoupling_aerobico_%"]
        assessment = "ottimo" if dec < 5 else "accettabile" if dec < 8 else "elevato"
        analysis_parts.append(f"Decoupling: {dec:.1f}% ({assessment})")
    if act.get("fc_media"):
        analysis_parts.append(f"FC: {act['fc_media']:.0f}/{act.get('fc_max', '?')} bpm")

    analysis_text = "\n".join(analysis_parts) if analysis_parts else None

    return {
        "id": garmin_id,
        "name": name,
        "sport": sport,
        "start_time": f"{date_str}T08:00:00" if date_str else None,
        "duration_secs": duration_secs,
        "distance_m": distance_m,
        "avg_hr": int(act["fc_media"]) if act.get("fc_media") else None,
        "max_hr": act.get("fc_max"),
        "avg_power": int(act["potenza_media"]) if act.get("potenza_media") else None,
        "max_power": act.get("potenza_max"),
        "normalized_power": int(act["potenza_normalizzata"]) if act.get("potenza_normalizzata") else None,
        "tss": act.get("TSS"),
        "intensity_factor": act.get("IF"),
        "avg_cadence": int(act["cadenza_media"]) if act.get("cadenza_media") else (int(act["cadenza"]) if act.get("cadenza") else None),
        "calories": None,
        "elevation_gain": act.get("dislivello_positivo") or act.get("dislivello_pos") or act.get("disliv_pos"),
        "avg_speed": (act.get("velocita_media_kmh") or act.get("vel_media") or 0) / 3.6 if act.get("velocita_media_kmh") or act.get("vel_media") else None,
        "raw_data": raw_data,
        "splits_data": splits_data,
        "analyzed": bool(analysis_text),
        "analysis_text": analysis_text,
    }


def main():
    print(f"Loading {ARCHIVE_PATH}...")
    with open(ARCHIVE_PATH) as f:
        data = json.load(f)

    activities = data.get("attivita", [])
    print(f"Found {len(activities)} activities")

    # Convert all
    converted = []
    skipped = 0
    for act in activities:
        result = convert_activity(act)
        if result:
            converted.append(result)
        else:
            skipped += 1

    print(f"Converted: {len(converted)}, Skipped (no ID): {skipped}")

    # Import via direct DB insert using SQLAlchemy
    # We'll use the Railway DATABASE_URL
    import os
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("ERROR: Set DATABASE_URL env var (Railway PostgreSQL URL)")
        print("Example: DATABASE_URL=postgresql://user:pass@host:port/db python3 scripts/import_archive.py")
        sys.exit(1)

    # Use psycopg2 for sync insert
    try:
        import psycopg2
        from psycopg2.extras import Json
    except ImportError:
        print("Installing psycopg2...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "psycopg2-binary"])
        import psycopg2
        from psycopg2.extras import Json

    # Fix URL scheme
    if db_url.startswith("postgresql+asyncpg://"):
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    # Check existing
    cur.execute("SELECT id FROM activities")
    existing_ids = {row[0] for row in cur.fetchall()}
    print(f"Existing activities in DB: {len(existing_ids)}")

    inserted = 0
    errors = 0
    for act in converted:
        if act["id"] in existing_ids:
            continue
        try:
            cur.execute("""
                INSERT INTO activities (id, name, sport, start_time, duration_secs, distance_m,
                    avg_hr, max_hr, avg_power, max_power, normalized_power, tss, intensity_factor,
                    avg_cadence, calories, elevation_gain, avg_speed, raw_data, splits_data,
                    analyzed, analysis_text, created_at)
                VALUES (%(id)s, %(name)s, %(sport)s, %(start_time)s, %(duration_secs)s, %(distance_m)s,
                    %(avg_hr)s, %(max_hr)s, %(avg_power)s, %(max_power)s, %(normalized_power)s, %(tss)s, %(intensity_factor)s,
                    %(avg_cadence)s, %(calories)s, %(elevation_gain)s, %(avg_speed)s, %(raw_data)s, %(splits_data)s,
                    %(analyzed)s, %(analysis_text)s, NOW())
            """, {
                **act,
                "raw_data": Json(act["raw_data"]),
                "splits_data": Json(act["splits_data"]),
            })
            inserted += 1
            if inserted % 100 == 0:
                conn.commit()
                print(f"  Inserted {inserted}...")
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  Error inserting {act['id']}: {e}")
            conn.rollback()

    conn.commit()
    cur.close()
    conn.close()

    print(f"\nDone! Inserted: {inserted}, Errors: {errors}, Already existed: {len(existing_ids)}")


if __name__ == "__main__":
    main()
