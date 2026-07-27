#!/usr/bin/env python3
"""
SALVI GIS — Reparación de base de datos y creación de usuario
Ejecutar una vez si la base de datos está dañada o no existe el usuario.

Uso:   python fix_db.py
"""
import sqlite3, hashlib, base64, os, shutil, uuid, getpass, sys

HERE    = os.path.dirname(os.path.abspath(__file__))
DB      = os.path.join(HERE, "db", "salvi_gis.db")
BACKUP  = os.path.join(HERE, "db", "salvi_gis - copia.db")

def hash_pw(pw: str) -> str:
    salt = os.urandom(32)
    key  = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 600_000)
    return base64.b64encode(salt + key).decode()

def db_is_ok(path):
    try:
        conn = sqlite3.connect(path)
        r = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        return r and r[0] == "ok"
    except Exception:
        return False

def add_missing_tables(conn):
    conn.executescript("""
CREATE TABLE IF NOT EXISTS project_ui_config (
    project_id TEXT NOT NULL, config_key TEXT NOT NULL,
    config_value TEXT DEFAULT '{}', updated_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (project_id, config_key));
CREATE TABLE IF NOT EXISTS zone_trees (
    zone_id TEXT PRIMARY KEY, trees TEXT DEFAULT '[]',
    loaded_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE,
    email TEXT DEFAULT '', password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'user', active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')), last_login TEXT DEFAULT NULL);
""")
    for sql in [
        "ALTER TABLE zones ADD COLUMN osm_relation INTEGER DEFAULT NULL",
    ]:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()

def create_or_reset_user(conn, username, password, email="", role="admin"):
    existing = conn.execute(
        "SELECT id FROM users WHERE lower(username)=lower(?)", (username,)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE users SET password_hash=?, active=1, role=? WHERE id=?",
            (hash_pw(password), role, existing[0])
        )
        print(f"  ✓ Contraseña actualizada para '{username}'.")
    else:
        uid = str(uuid.uuid4())[:12]
        conn.execute(
            "INSERT INTO users (id,username,email,password_hash,role,active) VALUES (?,?,?,?,?,1)",
            (uid, username, email, hash_pw(password), role)
        )
        print(f"  ✓ Usuario '{username}' creado (id={uid}).")
    conn.commit()

def main():
    print("\n══════════════════════════════════════════")
    print("  SALVI GIS — Reparación de base de datos")
    print("══════════════════════════════════════════\n")

    # Step 1: check if live DB is ok
    if db_is_ok(DB):
        print("✓ La base de datos principal está en buen estado.")
    else:
        print("⚠ La base de datos principal está dañada o falta.")
        if not os.path.exists(BACKUP):
            print(f"ERROR: No se encontró la copia de seguridad en:\n  {BACKUP}")
            sys.exit(1)
        print(f"  Restaurando desde: {os.path.basename(BACKUP)} …")
        shutil.copy2(BACKUP, DB)
        if not db_is_ok(DB):
            print("ERROR: La copia de seguridad también está dañada. Contacta soporte.")
            sys.exit(1)
        print("  ✓ Base de datos restaurada correctamente.")

    # Step 2: add missing tables / columns
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    add_missing_tables(conn)
    print("✓ Esquema actualizado.")

    # Step 3: list existing users
    users = conn.execute("SELECT username, role, active FROM users").fetchall()
    if users:
        print(f"\nUsuarios existentes ({len(users)}):")
        for u in users:
            print(f"  {'✓' if u['active'] else '✗'}  {u['username']}  [{u['role']}]")
    else:
        print("\nNo hay usuarios — se creará el administrador.")

    # Step 4: create/reset user
    print("\n──────────────────────────────────────────")
    print("  Crear o restablecer contraseña de usuario")
    print("──────────────────────────────────────────")
    username = input("Nombre de usuario [elizalde]: ").strip() or "elizalde"
    email    = input("Email [elizalde@salvi.es]: ").strip() or "elizalde@salvi.es"
    while True:
        pw  = getpass.getpass("Contraseña (mín. 8 caracteres): ")
        pw2 = getpass.getpass("Confirmar contraseña: ")
        if pw != pw2:
            print("  Las contraseñas no coinciden.")
        elif len(pw) < 8:
            print("  Mínimo 8 caracteres.")
        else:
            break

    create_or_reset_user(conn, username, pw, email, role="admin")
    conn.close()

    print("\n✓ Todo listo. Puedes iniciar el servidor con:")
    print("    python api_server.py\n")

if __name__ == "__main__":
    main()
