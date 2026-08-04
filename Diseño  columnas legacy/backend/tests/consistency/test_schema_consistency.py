"""
Salvi Studio · Columns — Tests de consistencia de esquema
==========================================================
Verificaciones estáticas que detectan errores de esquema ANTES de llegar
a PostgreSQL. Cada test codifica una clase de bug encontrada en producción:

  T1   Sintaxis válida en todos los .py del backend (detecta truncados OneDrive)
  T2   Sin bytes nulos en archivos fuente (corrupción de sincronización)
  T3   Sin nombres de tabla duplicados entre modelos
  T4   Sin nombres de tabla duplicados entre migraciones
  T5   Sin tipos enum PG duplicados entre migraciones
  T5b  Sin recreación implícita de un tipo enum ya creado explícitamente
  T6   Sin atributos reservados de SQLAlchemy (metadata, query, registry)
  T7   Toda FK de modelos apunta a una tabla definida
  T8   Toda FK de migraciones apunta a tabla ya creada (orden correcto)
  T9   Todo server_default de columna enum es un valor válido del tipo
  T10  Todo default=Enum.MIEMBRO en modelos referencia un miembro existente
  T11  Valores de enums de modelos ⊆ valores del tipo PG en migraciones
  T12  Todo tipo PG usado por un modelo existe en alguna migración

Ejecutar:  pytest tests/consistency/ -v
"""
import ast
import os
import re
from collections import defaultdict
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
APP_DIR = BACKEND / "app"
MODEL_DIR = APP_DIR / "models" / "db"
MIG_DIR = BACKEND / "migrations" / "versions"

RESERVED_ATTRS = {"metadata", "query", "registry"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def read_clean(path: Path) -> str:
    """Lee un archivo eliminando null-bytes (protección OneDrive)."""
    return path.read_bytes().rstrip(b"\x00").decode("utf-8", errors="replace")


def all_py(directory: Path):
    for p in sorted(directory.rglob("*.py")):
        if "__pycache__" in str(p):
            continue
        yield p


def extract_calls(raw: str, fn: str = "sa.Column("):
    """Extrae cada llamada fn(...) con paréntesis balanceados."""
    out, idx = [], 0
    while True:
        start = raw.find(fn, idx)
        if start == -1:
            break
        i = start + len(fn) - 1
        depth, j = 0, i
        while j < len(raw):
            if raw[j] == "(":
                depth += 1
            elif raw[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        out.append((start, raw[start : j + 1]))
        idx = j
    return out


def migration_order():
    """Orden real de aplicación según cadena down_revision."""
    files = {}
    for f in sorted(os.listdir(MIG_DIR)):
        if not f.endswith(".py"):
            continue
        raw = read_clean(MIG_DIR / f)
        rev = re.search(r'^revision\s*=\s*["\']([^"\']+)["\']', raw, re.MULTILINE)
        down = re.search(
            r'^down_revision\s*=\s*(None|["\']([^"\']+)["\'])', raw, re.MULTILINE
        )
        if rev:
            files[rev.group(1)] = {
                "file": f,
                "down": down.group(2) if down and down.group(2) else None,
                "raw": raw,
            }
    by_down = {v["down"]: k for k, v in files.items()}
    order, cur = [], by_down.get(None)
    while cur:
        order.append(cur)
        cur = by_down.get(cur)
    assert len(order) == len(files), "Cadena down_revision rota o bifurcada"
    return [files[r] for r in order]


def collect_migration_enums():
    """Todos los tipos enum PG creados en migraciones, con sus valores."""
    enum_values: dict[str, set] = {}
    for mig in migration_order():
        raw = mig["raw"]
        for m in re.finditer(
            r"CREATE TYPE\s+(\w+)\s+AS ENUM\s*\(([^)]*)\)", raw, re.DOTALL
        ):
            enum_values[m.group(1)] = set(re.findall(r"'([^']+)'", m.group(2)))
        lm = re.search(r"^ENUMS\s*=\s*\[(.*?)^\]", raw, re.DOTALL | re.MULTILINE)
        if lm:
            try:
                for name, values in ast.literal_eval("[" + lm.group(1) + "]"):
                    enum_values[name] = set(values)
            except (ValueError, SyntaxError):
                pass
        for m in re.finditer(r"postgresql\.ENUM\(([^)]*)\)", raw, re.DOTALL):
            args = m.group(1)
            nm = re.search(r"name\s*=\s*[\"'](\w+)[\"']", args)
            if nm and "create_type=False" not in args:
                vals = set(re.findall(r"[\"']([\w]+)[\"']\s*,", args))
                if vals:
                    enum_values.setdefault(nm.group(1), set()).update(vals)
        for m in re.finditer(r"(?<!\.)sa\.Enum\(([^)]*)\)", raw, re.DOTALL):
            args = m.group(1)
            nm = re.search(r"name\s*=\s*[\"'](\w+)[\"']", args)
            if nm:
                vals = set(
                    re.findall(r"[\"']([\w]+)[\"']", args.split("name=")[0])
                )
                if vals:
                    enum_values.setdefault(nm.group(1), set()).update(vals)
    return enum_values


def python_enum_classes(raw: str):
    """Clases Enum de un módulo: nombre -> (miembros, valores)."""
    out = {}
    try:
        tree = ast.parse(raw)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = [
                b.attr if isinstance(b, ast.Attribute) else getattr(b, "id", "")
                for b in node.bases
            ]
            if any("Enum" in b for b in bases):
                members, values = set(), set()
                for st in node.body:
                    if isinstance(st, ast.Assign) and isinstance(
                        st.targets[0], ast.Name
                    ):
                        members.add(st.targets[0].id)
                        if isinstance(st.value, ast.Constant):
                            values.add(str(st.value.value))
                out[node.name] = (members, values)
    return out


# ── T1 / T2: integridad de archivos ──────────────────────────────────────────

def test_t1_all_files_parse():
    errors = []
    for p in all_py(APP_DIR):
        try:
            ast.parse(read_clean(p))
        except SyntaxError as e:
            errors.append(f"{p.relative_to(BACKEND)}: línea {e.lineno}: {e.msg}")
    assert not errors, "Archivos con error de sintaxis:\n" + "\n".join(errors)


def test_t2_no_null_bytes():
    dirty = [
        str(p.relative_to(BACKEND))
        for p in list(all_py(APP_DIR)) + list(all_py(MIG_DIR))
        if b"\x00" in p.read_bytes()
    ]
    assert not dirty, "Archivos con null-bytes (truncados por OneDrive):\n" + "\n".join(dirty)


# ── T3 / T4: tablas duplicadas ────────────────────────────────────────────────

def test_t3_no_duplicate_tables_in_models():
    tables = defaultdict(list)
    for p in all_py(MODEL_DIR):
        raw = read_clean(p)
        for m in re.finditer(r'__tablename__\s*=\s*["\']([^"\']+)["\']', raw):
            tables[m.group(1)].append(p.name)
    dups = {t: fs for t, fs in tables.items() if len(fs) > 1}
    assert not dups, f"Tablas duplicadas en modelos: {dups}"


def test_t4_no_duplicate_tables_in_migrations():
    created = {}
    dups = []
    for mig in migration_order():
        for m in re.finditer(
            r'op\.create_table\(\s*["\'](\w+)["\']', mig["raw"]
        ):
            t = m.group(1)
            if t in created:
                dups.append(f"'{t}': {created[t]} y {mig['file']}")
            created[t] = mig["file"]
    assert not dups, "Tablas creadas dos veces:\n" + "\n".join(dups)


# ── T5 / T5b: enums PG duplicados o recreados implícitamente ────────────────

def test_t5_no_duplicate_pg_enum_types():
    created = {}
    dups = []
    for mig in migration_order():
        raw = mig["raw"]
        types_here = set()
        for m in re.finditer(r"CREATE TYPE\s+(\w+)\s+AS ENUM", raw):
            types_here.add(m.group(1))
        lm = re.search(r"^ENUMS\s*=\s*\[(.*?)^\]", raw, re.DOTALL | re.MULTILINE)
        if lm:
            try:
                for name, _ in ast.literal_eval("[" + lm.group(1) + "]"):
                    types_here.add(name)
            except (ValueError, SyntaxError):
                pass
        for m in re.finditer(r"postgresql\.ENUM\(([^)]*)\)", raw, re.DOTALL):
            args = m.group(1)
            nm = re.search(r"name\s*=\s*[\"'](\w+)[\"']", args)
            if nm and "create_type=False" not in args:
                types_here.add(nm.group(1))
        for t in types_here:
            if t in created:
                dups.append(f"'{t}': {created[t]} y {mig['file']}")
            else:
                created[t] = mig["file"]
    assert not dups, "Tipos enum creados dos veces:\n" + "\n".join(dups)


def test_t5b_no_implicit_recreate_of_explicit_enum_types():
    """
    Si un tipo ya se creó explícitamente (CREATE TYPE ... / ENUMS = [...]),
    ninguna columna posterior debe usar sa.Enum(...)/postgresql.ENUM(...) para
    ese mismo nombre SIN create_type=False — SQLAlchemy intentaría recrearlo
    (auto-create por defecto) y Postgres lanzaría DuplicateObject.
    Bug real: 0007/0008/0011/0012 tenían 59 columnas así.
    """
    bad = []
    for mig in migration_order():
        raw = mig["raw"]
        explicit = set(re.findall(r"CREATE TYPE\s+(\w+)\s+AS ENUM", raw))
        lm = re.search(r"^ENUMS\s*=\s*\[(.*?)^\]", raw, re.DOTALL | re.MULTILINE)
        if lm:
            try:
                for name, _ in ast.literal_eval("[" + lm.group(1) + "]"):
                    explicit.add(name)
            except (ValueError, SyntaxError):
                pass
        if not explicit:
            continue
        for m in re.finditer(r"sa\.Enum\(([^)]*)\)", raw, re.DOTALL):
            args = m.group(1)
            nm = re.search(r"name\s*=\s*[\"'](\w+)[\"']", args)
            if nm and nm.group(1) in explicit and "create_type=False" not in args:
                line = raw[: m.start()].count("\n") + 1
                bad.append(
                    f"{mig['file']}:{line}: sa.Enum(name='{nm.group(1)}') "
                    f"recrea un tipo ya creado explícitamente — falta create_type=False"
                )
        for m in re.finditer(r"postgresql\.ENUM\(([^)]*)\)", raw, re.DOTALL):
            args = m.group(1)
            nm = re.search(r"name\s*=\s*[\"'](\w+)[\"']", args)
            if nm and nm.group(1) in explicit and "create_type=False" not in args:
                line = raw[: m.start()].count("\n") + 1
                bad.append(
                    f"{mig['file']}:{line}: postgresql.ENUM(name='{nm.group(1)}') "
                    f"recrea un tipo ya creado explícitamente — falta create_type=False"
                )
    assert not bad, "\n".join(bad)


# ── T6: atributos reservados ─────────────────────────────────────────────────

def test_t6_no_reserved_attribute_names():
    bad = []
    for p in all_py(MODEL_DIR):
        raw = read_clean(p)
        for m in re.finditer(r"^\s{4}(\w+)\s*=\s*(?:Column|mapped_column)\(", raw, re.MULTILINE):
            if m.group(1) in RESERVED_ATTRS:
                line = raw[: m.start()].count("\n") + 1
                bad.append(f"{p.name}:{line}: atributo reservado '{m.group(1)}'")
    assert not bad, "\n".join(bad)


# ── T7 / T8: integridad de FKs ───────────────────────────────────────────────

def _model_tables():
    tables = set()
    for p in all_py(MODEL_DIR):
        raw = read_clean(p)
        tables.update(
            re.findall(r'__tablename__\s*=\s*["\']([^"\']+)["\']', raw)
        )
    return tables


def test_t7_model_fks_target_existing_tables():
    tables = _model_tables()
    bad = []
    for p in all_py(MODEL_DIR):
        raw = read_clean(p)
        for m in re.finditer(r'ForeignKey\(["\'](\w+)\.', raw):
            if m.group(1) not in tables:
                bad.append(f"{p.name}: FK a tabla inexistente '{m.group(1)}'")
    assert not bad, "\n".join(sorted(set(bad)))


def test_t8_migration_fks_in_creation_order():
    created = set()
    bad = []
    for mig in migration_order():
        raw = mig["raw"]
        blocks = re.split(r"op\.create_table\(", raw)
        for block in blocks[1:]:
            m = re.match(r'\s*["\'](\w+)["\']', block)
            if not m:
                continue
            tname = m.group(1)
            end = re.search(r"\n    op\.\w+\(", block)
            segment = block[: end.start()] if end else block
            for fk in re.findall(r'ForeignKey\(["\'](\w+)\.', segment):
                if fk != tname and fk not in created:
                    bad.append(
                        f"{mig['file']}: '{tname}' FK -> '{fk}' aún no creada"
                    )
            created.add(tname)
    assert not bad, "\n".join(bad)


# ── T9: server_default válidos ───────────────────────────────────────────────

def test_t9_enum_server_defaults_are_valid():
    enum_values = collect_migration_enums()
    bad = []
    for mig in migration_order():
        raw = mig["raw"]
        for pos, col in extract_calls(raw):
            m = re.search(r'ENUM\(\s*name\s*=\s*[\"\'](\w+)[\"\']', col) or re.search(
                r'sa\.Enum\([^)]*name\s*=\s*[\"\'](\w+)[\"\']', col, re.DOTALL
            )
            if not m:
                continue
            tname = m.group(1)
            d = re.search(r'server_default\s*=\s*[\"\']([\w\.]+)[\"\']', col)
            if not d:
                continue
            line = raw[:pos].count("\n") + 1
            if tname not in enum_values:
                bad.append(f"{mig['file']}:{line}: tipo '{tname}' nunca creado")
            elif d.group(1) not in enum_values[tname]:
                bad.append(
                    f"{mig['file']}:{line}: '{tname}' default '{d.group(1)}' "
                    f"no está en {sorted(enum_values[tname])}"
                )
    assert not bad, "\n".join(bad)


# ── T10: default=Enum.MIEMBRO existe ─────────────────────────────────────────

def test_t10_model_enum_defaults_reference_existing_members():
    bad = []
    for p in all_py(MODEL_DIR):
        raw = read_clean(p)
        classes = python_enum_classes(raw)
        for m in re.finditer(r"default\s*=\s*(\w+)\.(\w+)", raw):
            cls, member = m.group(1), m.group(2)
            if cls in classes and member not in classes[cls][0]:
                line = raw[: m.start()].count("\n") + 1
                bad.append(
                    f"{p.name}:{line}: default={cls}.{member} — miembro inexistente "
                    f"(disponibles: {sorted(classes[cls][0])})"
                )
    assert not bad, "\n".join(bad)


# ── T11 / T12: coherencia modelo ↔ migración ─────────────────────────────────

def test_t11_t12_model_enums_match_migration_types():
    enum_values = collect_migration_enums()
    bad = []
    for p in all_py(MODEL_DIR):
        raw = read_clean(p)
        classes = python_enum_classes(raw)
        for m in re.finditer(
            r'Enum\(\s*(\w+)\s*,\s*name\s*=\s*[\"\'](\w+)[\"\']', raw
        ):
            pycls, pgname = m.group(1), m.group(2)
            if pycls not in classes:
                continue
            _, values = classes[pycls]
            if pgname not in enum_values:
                bad.append(
                    f"{p.name}: tipo PG '{pgname}' no existe en ninguna migración (T12)"
                )
            else:
                missing = values - enum_values[pgname]
                if missing:
                    bad.append(
                        f"{p.name}: '{pgname}' valores del modelo {sorted(missing)} "
                        f"faltan en el tipo PG {sorted(enum_values[pgname])} (T11)"
                    )
    assert not bad, "\n".join(bad)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
