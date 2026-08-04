#!/usr/bin/env python3
"""SALVI Solar — Database layer. SQLite stdlib."""
import sqlite3, os, json, uuid
from datetime import datetime
from contextlib import contextmanager

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'db', 'salvi_solar.db')

@contextmanager
def db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                country TEXT DEFAULT 'ES',
                city TEXT DEFAULT '',
                latitude REAL,
                longitude REAL,
                road_type TEXT DEFAULT '',
                lighting_class TEXT DEFAULT 'M4',
                library_version TEXT DEFAULT 'Salvi Solar 2026.1',
                currency TEXT DEFAULT 'EUR',
                language TEXT DEFAULT 'ES',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS pvgis_cache (
                cache_key TEXT PRIMARY KEY,
                lat REAL, lon REAL,
                tilt REAL, azimuth REAL,
                peak_power_kw REAL,
                losses_pct REAL,
                pvgis_db TEXT,
                data_json TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT,
                pv_peak_power_wp REAL,
                battery_nominal_wh REAL,
                weight_kg REAL,
                geometry_type TEXT,
                official INTEGER DEFAULT 1,
                library_version TEXT DEFAULT 'Salvi Solar 2026.1',
                extra_json TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS cost_library (
                version TEXT PRIMARY KEY,
                data_json TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS simulation_runs (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                params_json TEXT,
                status TEXT DEFAULT 'completed'
            );
            CREATE TABLE IF NOT EXISTS local_shading_analysis (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                provider TEXT DEFAULT 'SHADOWMAP',
                shading_mode TEXT,
                lat REAL,
                lon REAL,
                panel_center_height_m REAL,
                height_mode TEXT,
                provider_confidence REAL,
                annual_direct_shadow_loss_pct REAL,
                annual_total_shadow_loss_pct REAL,
                monthly_shadow_loss_pct TEXT,
                critical_month_shadow_loss_pct REAL,
                status TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                source_payload_hash TEXT
            );
        """)
        # Seed products if empty
        count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        if count == 0:
            products = [
                ("SIL_M_60","SIL M 60","SIL",60,360,10,"sil_horizontal",1),
                ("SIL_M_90","SIL M 90","SIL",90,720,14,"sil_horizontal",1),
                ("SIL_L_200","SIL L 200","SIL",200,1080,40,"sil_horizontal",1),
                ("SIL_L_260","SIL L 260","SIL",260,1330,55,"sil_horizontal",1),
                ("SIL_IND","SIL Panel Independiente","SIL",0,0,0,"sil_independent",1),
                ("CIL_250","Cilindro Solar 250mm – 245 Wp","CILINDRO",245,1080,25,"cylinder_250",1),
                ("CIL_300","Cilindro Solar 300mm – 294 Wp","CILINDRO",294,1080,28,"cylinder_300",1),
                ("CIL_350","Cilindro Solar 350mm – 343 Wp","CILINDRO",343,1330,32,"cylinder_350",1),
                ("DOBLE_EO","Doble Panel Vertical E-O – 200 Wp","PANEL",200,1080,30,"double_vertical_eo",1),
                ("CUSTOM_OPT","Custom Orientable (dimensionado a medida)","CUSTOM",0,0,0,"custom_orientable",1),
            ]
            conn.executemany(
                "INSERT INTO products (id,name,category,pv_peak_power_wp,battery_nominal_wh,weight_kg,geometry_type,official) VALUES (?,?,?,?,?,?,?,?)",
                products
            )
        # Always keep modular product names in sync (Wp label may have changed)
        modular_names = [
            ("Cilindro Solar 250mm – 245 Wp", "CIL_250"),
            ("Cilindro Solar 300mm – 294 Wp", "CIL_300"),
            ("Cilindro Solar 350mm – 343 Wp", "CIL_350"),
            ("Doble Panel Vertical E-O – 200 Wp", "DOBLE_EO"),
            ("Custom Orientable (dimensionado a medida)", "CUSTOM_OPT"),
        ]
        for new_name, pid in modular_names:
            conn.execute("UPDATE products SET name=? WHERE id=? AND name!=?", (new_name, pid, new_name))
        # SIL_IND is now sized by the optimizer (like CUSTOM_OPT) — clear any stale fixed specs
        conn.execute(
            "UPDATE products SET pv_peak_power_wp=0, battery_nominal_wh=0, weight_kg=0 "
            "WHERE id='SIL_IND' AND pv_peak_power_wp!=0"
        )
        # Seed cost library if empty
        count = conn.execute("SELECT COUNT(*) FROM cost_library").fetchone()[0]
        if count == 0:
            costs = {
                "panel_eur_wp": 0.18,
                "battery_eur_wh": 0.11,
                "controller_eur": 17,
                "presence_sensor_eur": 10,
                "smartec_node_eur": 22,
                "gateway_eur": 20,
                "installation_eur": 80,
                "structure_eur": 100,
                "cleaning_annual_eur": 25,
                "maintenance_annual_eur": 25,
                "battery_replacement_eur": 200,
                "gross_margin": 0.62
            }
            conn.execute(
                "INSERT INTO cost_library (version, data_json) VALUES (?, ?)",
                ("Salvi Solar 2026.1", json.dumps(costs))
            )

# Project CRUD
def create_project(data):
    pid = str(uuid.uuid4())
    with db() as conn:
        conn.execute("""INSERT INTO projects (id,name,country,city,latitude,longitude,road_type,lighting_class,library_version,currency,language)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (pid, data.get('name','Sin nombre'), data.get('country','ES'),
             data.get('city',''), data.get('latitude'), data.get('longitude'),
             data.get('road_type',''), data.get('lighting_class','M4'),
             data.get('library_version','Salvi Solar 2026.1'),
             data.get('currency','EUR'), data.get('language','ES')))
    return get_project(pid)

def get_project(pid):
    with db() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        return dict(row) if row else None

def list_projects():
    with db() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
        return [dict(r) for r in rows]

def update_project(pid, data):
    fields = ['name','country','city','latitude','longitude','road_type','lighting_class','currency','language']
    updates = {k: data[k] for k in fields if k in data}
    updates['updated_at'] = datetime.now().isoformat()
    if not updates:
        return get_project(pid)
    sets = ', '.join(f"{k}=?" for k in updates)
    with db() as conn:
        conn.execute(f"UPDATE projects SET {sets} WHERE id=?", list(updates.values()) + [pid])
    return get_project(pid)

def delete_project(pid):
    with db() as conn:
        conn.execute("DELETE FROM projects WHERE id=?", (pid,))

# Local shading analysis (Shadowmap correction results)
def save_shading_analysis(data):
    aid = str(uuid.uuid4())
    with db() as conn:
        conn.execute("""INSERT INTO local_shading_analysis
            (id,project_id,provider,shading_mode,lat,lon,panel_center_height_m,height_mode,
             provider_confidence,annual_direct_shadow_loss_pct,annual_total_shadow_loss_pct,
             monthly_shadow_loss_pct,critical_month_shadow_loss_pct,status,source_payload_hash)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (aid, data.get('project_id'), data.get('provider', 'SHADOWMAP'),
             data.get('shading_mode'), data.get('lat'), data.get('lon'),
             data.get('panel_center_height_m'), data.get('height_mode'),
             data.get('provider_confidence'),
             data.get('annual_direct_shadow_loss_pct'), data.get('annual_total_shadow_loss_pct'),
             json.dumps(data.get('monthly_shadow_loss_pct', [])),
             data.get('critical_month_shadow_loss_pct'), data.get('status'),
             data.get('source_payload_hash')))
    return get_shading_analysis(aid)

def get_shading_analysis(aid):
    with db() as conn:
        row = conn.execute("SELECT * FROM local_shading_analysis WHERE id=?", (aid,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result['monthly_shadow_loss_pct'] = json.loads(result['monthly_shadow_loss_pct'] or '[]')
        return result

def list_shading_analyses(project_id):
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM local_shading_analysis WHERE project_id=? ORDER BY created_at DESC",
            (project_id,)
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d['monthly_shadow_loss_pct'] = json.loads(d['monthly_shadow_loss_pct'] or '[]')
            out.append(d)
        return out

# PVGIS cache
def get_pvgis_cache(key):
    with db() as conn:
        row = conn.execute("SELECT data_json FROM pvgis_cache WHERE cache_key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

def set_pvgis_cache(key, lat, lon, tilt, azimuth, peak_kw, losses, pvgis_db, data):
    with db() as conn:
        conn.execute("""INSERT OR REPLACE INTO pvgis_cache 
            (cache_key,lat,lon,tilt,azimuth,peak_power_kw,losses_pct,pvgis_db,data_json)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (key, lat, lon, tilt, azimuth, peak_kw, losses, pvgis_db, json.dumps(data)))

def get_all_products():
    with db() as conn:
        rows = conn.execute("SELECT * FROM products ORDER BY category, pv_peak_power_wp").fetchall()
        return [dict(r) for r in rows]

def get_product(pid):
    with db() as conn:
        row = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        return dict(row) if row else None

def get_cost_library():
    with db() as conn:
        row = conn.execute("SELECT * FROM cost_library ORDER BY updated_at DESC LIMIT 1").fetchone()
        if row:
            d = dict(row)
            d['data'] = json.loads(d['data_json'])
            return d
        return None
