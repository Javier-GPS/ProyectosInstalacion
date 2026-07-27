#!/usr/bin/env python3
"""
SALVI GIS — Utilidad de gestión de usuarios
Uso: python reset_password.py [opción]

Opciones:
  (sin args)     Modo interactivo: listar usuarios, resetear contraseña o crear admin
  --list         Listar todos los usuarios
  --reset USER   Resetear contraseña de un usuario
  --create       Crear nuevo usuario administrador
  --delete USER  Eliminar (desactivar) un usuario
"""
import sys, os, sqlite3, hashlib, base64, os as _os, getpass

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db", "salvi_gis.db")

def _hash_pw(pw: str) -> str:
    salt = _os.urandom(32)
    key  = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 600_000)
    return base64.b64encode(salt + key).decode()

def get_conn():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Base de datos no encontrada en:\n  {DB_PATH}")
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def list_users():
    conn = get_conn()
    rows = conn.execute(
        "SELECT username, email, role, active, last_login FROM users ORDER BY username"
    ).fetchall()
    conn.close()
    if not rows:
        print("No hay usuarios registrados.")
        return
    print(f"\n{'USUARIO':<20} {'EMAIL':<30} {'ROL':<8} {'ACTIVO':<8} {'ÚLTIMO ACCESO'}")
    print("-" * 80)
    for r in rows:
        active = "✓" if r["active"] else "✗"
        login  = r["last_login"] or "nunca"
        print(f"{r['username']:<20} {(r['email'] or ''):<30} {r['role']:<8} {active:<8} {login}")
    print()

def reset_password(username=None):
    conn = get_conn()
    if not username:
        username = input("Usuario a resetear: ").strip()
    row = conn.execute(
        "SELECT id, username, role FROM users WHERE lower(username)=lower(?)", (username,)
    ).fetchone()
    if not row:
        print(f"ERROR: Usuario '{username}' no encontrado.")
        conn.close(); return
    print(f"Reseteando contraseña para: {row['username']} [{row['role']}]")
    while True:
        pw  = getpass.getpass("Nueva contraseña (mín. 8 caracteres): ")
        pw2 = getpass.getpass("Repetir contraseña: ")
        if pw != pw2:
            print("Las contraseñas no coinciden. Inténtalo de nuevo.")
        elif len(pw) < 8:
            print("La contraseña debe tener al menos 8 caracteres.")
        else:
            break
    conn.execute(
        "UPDATE users SET password_hash=?, active=1 WHERE id=?", (_hash_pw(pw), row["id"])
    )
    conn.commit(); conn.close()
    print(f"✓ Contraseña actualizada para '{row['username']}'. Ya puedes iniciar sesión.")

def create_admin():
    conn = get_conn()
    import uuid as _uuid
    username = input("Nombre de usuario (admin): ").strip()
    if not username:
        print("ERROR: El nombre no puede estar vacío."); conn.close(); return
    existing = conn.execute(
        "SELECT id FROM users WHERE lower(username)=lower(?)", (username,)
    ).fetchone()
    if existing:
        print(f"Ya existe un usuario con ese nombre. Usa --reset para cambiar su contraseña.")
        conn.close(); return
    email = input("Email (opcional, para recuperación): ").strip()
    while True:
        pw  = getpass.getpass("Contraseña (mín. 8 caracteres): ")
        pw2 = getpass.getpass("Repetir contraseña: ")
        if pw != pw2:
            print("Las contraseñas no coinciden.")
        elif len(pw) < 8:
            print("Mínimo 8 caracteres.")
        else:
            break
    uid = str(_uuid.uuid4())[:12]
    conn.execute(
        "INSERT INTO users (id,username,email,password_hash,role,active) VALUES (?,?,?,?,?,1)",
        (uid, username, email, _hash_pw(pw), "admin")
    )
    conn.commit(); conn.close()
    print(f"✓ Administrador '{username}' creado. Ya puedes iniciar sesión.")

def delete_user(username=None):
    conn = get_conn()
    if not username:
        username = input("Usuario a eliminar: ").strip()
    row = conn.execute(
        "SELECT id, username FROM users WHERE lower(username)=lower(?)", (username,)
    ).fetchone()
    if not row:
        print(f"ERROR: Usuario '{username}' no encontrado."); conn.close(); return
    confirm = input(f"¿Desactivar usuario '{row['username']}'? (s/N): ").strip().lower()
    if confirm == 's':
        conn.execute("UPDATE users SET active=0 WHERE id=?", (row["id"],))
        conn.commit()
        print(f"✓ Usuario '{row['username']}' desactivado.")
    else:
        print("Cancelado.")
    conn.close()

def interactive():
    print("\n══════════════════════════════════════")
    print("  SALVI GIS — Gestión de usuarios")
    print("══════════════════════════════════════")
    print("  1. Listar usuarios")
    print("  2. Resetear contraseña")
    print("  3. Crear administrador")
    print("  4. Desactivar usuario")
    print("  0. Salir")
    print("══════════════════════════════════════")
    opt = input("Opción: ").strip()
    if opt == "1":
        list_users()
    elif opt == "2":
        list_users()
        reset_password()
    elif opt == "3":
        create_admin()
    elif opt == "4":
        list_users()
        delete_user()
    elif opt == "0":
        sys.exit(0)
    else:
        print("Opción no válida.")

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        interactive()
    elif args[0] == "--list":
        list_users()
    elif args[0] == "--reset" and len(args) > 1:
        reset_password(args[1])
    elif args[0] == "--reset":
        reset_password()
    elif args[0] == "--create":
        create_admin()
    elif args[0] == "--delete" and len(args) > 1:
        delete_user(args[1])
    else:
        print(__doc__)
