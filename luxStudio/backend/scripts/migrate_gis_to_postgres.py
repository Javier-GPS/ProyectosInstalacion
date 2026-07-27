#!/usr/bin/env python3
"""Migrate SALVI GIS data from SQLite to PostgreSQL.

Usage:
    cd backend && python scripts/migrate_gis_to_postgres.py
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://luxstudio:luxstudio@localhost:5432/luxstudio")

from app.database import SessionLocal
from app.models import (
    User, Project,
    GisZone, GisZoneConfig, GisZoneOsmData, GisZoneTrees,
    GisLuminaire, GisInventoryLuminaire, GisPhotometricResult,
    GisProjectUiConfig, ensure_gis_tables,
)
# Note: hash_password was in services/auth.py which is now removed.
# Password migration is no longer needed — auth goes through OIDC.
GIS_DB_PATH = Path(__file__).resolve().parent.parent.parent / "GIS" / "db" / "salvi_gis.db"


def _json(v, default=None):
    if v is None:
        return default if default is not None else {}
    if isinstance(v, (list, dict)):
        return v
    try:
        return json.loads(v)
    except Exception:
        return default if default is not None else {}


def _f(v):
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


def migrate_users(sl, pg):
    rows = sl.execute("SELECT * FROM users").fetchall()
    m = {}
    for r in rows:
        d = dict(r)
        existing = pg.query(User).filter(
            (User.email == (d.get("email") or "").lower().strip()) |
            (User.name == d.get("username", "").strip())
        ).first()
        if existing:
            m[d["id"]] = existing.id
            continue
        u = User(
            name=d.get("username", "unknown").strip(),
            email=(d.get("email") or f"{d.get('username','user')}@salvi.lighting").lower().strip(),
            password_hash=d.get("password_hash", "") or "oidc",
            role="ADMIN" if d.get("role", "").lower() == "admin" else "USER",
            is_active=bool(d.get("active", 1)),
        )
        pg.add(u)
        pg.flush()
        m[d["id"]] = u.id
    pg.commit()
    return m


def migrate_projects(sl, pg, user_map):
    rows = sl.execute("SELECT * FROM projects").fetchall()
    m = {}
    for r in rows:
        d = dict(r)
        existing = pg.query(Project).filter(Project.project_name == d["name"].strip()).first()
        if existing:
            m[d["id"]] = existing.id
            continue
        p = Project(project_name=d["name"].strip(), owner_user_id=1, status="active")
        pg.add(p)
        pg.flush()
        m[d["id"]] = p.id
    pg.commit()
    return m


def migrate_zones(sl, pg, proj_map):
    rows = sl.execute("SELECT * FROM zones").fetchall()
    existing_ids = set()
    count = 0
    for r in rows:
        d = dict(r)
        if pg.get(GisZone, d["id"]):
            existing_ids.add(d["id"])
            continue
        pg.add(GisZone(
            id=d["id"], name=d["name"].strip(),
            type=d.get("type", "") or "", color=d.get("color") or "#4caf82",
            priority=d.get("priority") or 2,
            center_lat=_f(d.get("center_lat")), center_lon=_f(d.get("center_lon")),
            zoom=d.get("zoom") or 12, bbox=d.get("bbox") or "",
            description=d.get("description") or "",
            est={"primary": _f(d.get("est_primary")) or 0,
                 "secondary": _f(d.get("est_secondary")) or 0,
                 "tertiary": _f(d.get("est_tertiary")) or 0,
                 "residential": _f(d.get("est_residential")) or 0,
                 "unclassified": _f(d.get("est_unclassified")) or 0},
            corridors=_json(d.get("corridors"), []),
            bounds_polygon=_json(d.get("bounds_polygon"), []),
            osm_relation=d.get("osm_relation"),
            source=d.get("source") or "manual",
            project_id=proj_map.get(d.get("project_id")) if d.get("project_id") else None,
        ))
        existing_ids.add(d["id"])
        count += 1
    pg.commit()
    return existing_ids


def migrate_zone_configs(sl, pg, valid_zone_ids):
    rows = sl.execute("SELECT * FROM zone_config").fetchall()
    ok = 0
    skip = 0
    for r in rows:
        d = dict(r)
        if d["zone_id"] not in valid_zone_ids:
            skip += 1
            continue
        if pg.get(GisZoneConfig, d["zone_id"]):
            continue
        pg.add(GisZoneConfig(
            zone_id=d["zone_id"], spacing=d.get("spacing") or 30,
            watt_hps=_f(d.get("watt_hps")) or 150, watt_led=_f(d.get("watt_led")) or 60,
            efficacy=_f(d.get("efficacy")) or 90, hours_night=_f(d.get("hours_night")) or 11.5,
        ))
        ok += 1
    pg.commit()
    return ok, skip


def migrate_osm_data(sl, pg, valid_zone_ids):
    rows = sl.execute("SELECT * FROM zone_osm_data").fetchall()
    ok = 0
    for r in rows:
        d = dict(r)
        if d["zone_id"] not in valid_zone_ids:
            continue
        if pg.get(GisZoneOsmData, d["zone_id"]):
            continue
        pg.add(GisZoneOsmData(
            zone_id=d["zone_id"],
            km_by_type=_json(d.get("km_by_type"), {}),
            ways=_json(d.get("ways"), []),
            source=d.get("source") or "estimated",
        ))
        ok += 1
    pg.commit()
    return ok


def migrate_luminaires(sl, pg, valid_zone_ids, proj_map):
    rows = sl.execute("SELECT * FROM luminaires").fetchall()
    count = 0
    for r in rows:
        d = dict(r)
        if d["zone_id"] not in valid_zone_ids:
            continue
        old_pid = d.get("project_id")
        new_pid = proj_map.get(old_pid) if old_pid else None
        pg.add(GisLuminaire(
            project_id=new_pid, zone_id=d["zone_id"],
            road_type=d.get("road_type"), lighting_class=d.get("lighting_class"),
            street_name=d.get("street_name"), lat=d["lat"], lon=d["lon"],
            watts=_f(d.get("watts")), spacing=_f(d.get("spacing")),
            tilt=_f(d.get("tilt")), height_m=_f(d.get("height_m")),
            arm_len=_f(d.get("arm_len")), distribution=d.get("distribution"),
        ))
        count += 1
        if count % 5000 == 0:
            pg.commit()
    pg.commit()
    return count


def migrate_inventory(sl, pg, valid_zone_ids):
    rows = sl.execute("SELECT * FROM inventory_luminaires").fetchall()
    count = 0
    for r in rows:
        d = dict(r)
        if d["zone_id"] not in valid_zone_ids:
            continue
        pg.add(GisInventoryLuminaire(
            zone_id=d["zone_id"], point_id=d.get("point_id"),
            lat=d["lat"], lon=d["lon"],
            power_w=_f(d.get("power_w")), height_m=_f(d.get("height_m")),
            brand=d.get("brand"), model=d.get("model"),
            lamp_type=d.get("lamp_type"), support_type=d.get("support_type"),
            circuit_id=d.get("circuit_id"), line_id=d.get("line_id"),
            extra=_json(d.get("extra"), {}),
            way_key=d.get("way_key"), road_type=d.get("road_type"),
        ))
        count += 1
    pg.commit()
    return count


def migrate_photometric(sl, pg, valid_zone_ids):
    rows = sl.execute("SELECT * FROM photometric_results").fetchall()
    count = 0
    for r in rows:
        d = dict(r)
        if d["zone_id"] not in valid_zone_ids:
            continue
        pg.add(GisPhotometricResult(
            zone_id=d["zone_id"], segment_name=d.get("segment_name"),
            match_key=d.get("match_key"), road_width=_f(d.get("road_width")),
            spacing=_f(d.get("spacing")), lighting_class=d.get("lighting_class"),
            power_w=_f(d.get("power_w")), lm_em=_f(d.get("lm_em")),
            uo=_f(d.get("uo")), ui=_f(d.get("ui")), ti=_f(d.get("ti")),
            sr=_f(d.get("sr")), model=d.get("model"), lente=d.get("lente"),
            tilt=_f(d.get("tilt")), phi_lm=_f(d.get("phi_lm")),
            cumple=d.get("cumple"), notes=d.get("notes"),
        ))
        count += 1
    pg.commit()
    return count


def migrate_trees(sl, pg, valid_zone_ids):
    rows = sl.execute("SELECT * FROM zone_trees").fetchall()
    count = 0
    for r in rows:
        d = dict(r)
        if d["zone_id"] not in valid_zone_ids:
            continue
        if pg.get(GisZoneTrees, d["zone_id"]):
            continue
        pg.add(GisZoneTrees(zone_id=d["zone_id"], trees=_json(d.get("trees"), [])))
        count += 1
    pg.commit()
    return count


def migrate_ui_config(sl, pg, proj_map):
    rows = sl.execute("SELECT * FROM project_ui_config").fetchall()
    count = 0
    for r in rows:
        d = dict(r)
        new_pid = proj_map.get(d.get("project_id")) if d.get("project_id") else None
        if not new_pid:
            continue
        pg.add(GisProjectUiConfig(
            project_id=new_pid, config_key=d["config_key"],
            config_value=_json(d.get("config_value"), {}),
        ))
        count += 1
    pg.commit()
    return count


def main():
    if not GIS_DB_PATH.exists():
        print("ERROR: GIS SQLite DB not found at", GIS_DB_PATH)
        sys.exit(1)

    print("=" * 55)
    print("  SALVI GIS -> PostgreSQL Migration")
    print("=" * 55)

    ensure_gis_tables()

    sl = sqlite3.connect(str(GIS_DB_PATH))
    sl.row_factory = sqlite3.Row
    pg = SessionLocal()

    try:
        # 1. Users
        print("\n1. Users...", end=" ")
        user_map = migrate_users(sl, pg)
        print(f"{len(user_map)} mapped")

        # 2. Projects
        print("2. Projects...", end=" ")
        proj_map = migrate_projects(sl, pg, user_map)
        print(f"{len(proj_map)} mapped")

        # 3. Zones
        print("3. Zones...", end=" ")
        zone_ids = migrate_zones(sl, pg, proj_map)
        print(f"{len(zone_ids)} total")

        # 4. Zone configs
        print("4. Zone configs...", end=" ")
        ok, skip = migrate_zone_configs(sl, pg, zone_ids)
        print(f"{ok} ok, {skip} skipped (orphan)")

        # 5. OSM data
        print("5. OSM data...", end=" ")
        osm = migrate_osm_data(sl, pg, zone_ids)
        print(f"{osm} rows")

        # 6. Luminaires
        print("6. Luminaires...", end=" ")
        lum = migrate_luminaires(sl, pg, zone_ids, proj_map)
        print(f"{lum}")

        # 7. Inventory
        print("7. Inventory...", end=" ")
        inv = migrate_inventory(sl, pg, zone_ids)
        print(f"{inv} items")

        # 8. Photometric results
        print("8. Photometric results...", end=" ")
        photo = migrate_photometric(sl, pg, zone_ids)
        print(f"{photo} rows")

        # 9. Trees
        print("9. Trees...", end=" ")
        trees = migrate_trees(sl, pg, zone_ids)
        print(f"{trees} sets")

        # 10. UI config
        print("10. UI config...", end=" ")
        ui = migrate_ui_config(sl, pg, proj_map)
        print(f"{ui} rows")

        print("\n" + "=" * 55)
        print("  Migration complete!")
        print("=" * 55)

    except Exception as e:
        print(f"\n\nERROR: {e}")
        pg.rollback()
        raise
    finally:
        sl.close()
        pg.close()


if __name__ == "__main__":
    main()
