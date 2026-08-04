"""
Salvi Studio · Columns — Tests de aceptación Fase 1 (AC-01 a AC-15)
Sección 23, Fase 1.

Requiere: pytest-asyncio, httpx, base de datos de test.
Ejecutar: pytest tests/acceptance/ -v
"""
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.security import MaturityLevel, ProjectStatus


BASE = "/api/v1"


@pytest.fixture
def project_payload():
    return {
        "name": "Test Columnas Valencia",
        "country": "ES",
        "language": "es",
        "currency": "EUR",
        "timezone": "Europe/Madrid",
        "confidentiality": "internal",
    }


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── AC-01: Crear proyecto con datos mínimos ───────────────────────────────────
@pytest.mark.asyncio
async def test_ac01_create_project_minimal(client, project_payload):
    """AC-01: Crear proyecto con datos mínimos; código autogenerado; estado=borrador; madurez=M0."""
    r = await client.post(f"{BASE}/projects", json=project_payload)
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "draft"
    assert data["maturity"] == "M0"
    assert data["project_code"].startswith("COL-ES-")
    # Escenario base creado automáticamente (se verifica en AC-02)


# ── AC-02: Escenario base creado automáticamente ─────────────────────────────
@pytest.mark.asyncio
async def test_ac02_base_scenario_auto_created(client, project_payload):
    """AC-02: Al crear proyecto se genera escenario 'Base' automáticamente."""
    r = await client.post(f"{BASE}/projects", json=project_payload)
    project_id = r.json()["id"]

    r2 = await client.get(f"{BASE}/projects/{project_id}/scenarios")
    assert r2.status_code == 200
    scenarios = r2.json()
    base = [s for s in scenarios if s["is_base"]]
    assert len(base) == 1
    assert base[0]["name"] == "Base"


# ── AC-03: Crear escenario adicional ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_ac03_create_additional_scenario(client, project_payload):
    """AC-03: Un proyecto puede tener múltiples escenarios."""
    r = await client.post(f"{BASE}/projects", json=project_payload)
    project_id = r.json()["id"]

    r2 = await client.post(f"{BASE}/projects/{project_id}/scenarios", json={
        "name": "Escenario viento fuerte", "is_base": False
    })
    assert r2.status_code == 201
    assert r2.json()["name"] == "Escenario viento fuerte"


# ── AC-04: Crear revisión ─────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_ac04_create_revision(client, project_payload):
    """AC-04: Crear revisión técnica R00."""
    r = await client.post(f"{BASE}/projects", json=project_payload)
    project_id = r.json()["id"]

    r2 = await client.post(f"{BASE}/projects/{project_id}/revisions", json={
        "revision_code": "R00",
        "revision_type": "technical",
        "description": "Primera revisión técnica",
    })
    assert r2.status_code == 201
    data = r2.json()
    assert data["revision_code"] == "R00"
    assert data["is_frozen"] is False


# ── AC-05: Congelar revisión — P-01 ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_ac05_freeze_revision(client, project_payload):
    """AC-05: Congelar revisión crea snapshot e hash; revisión no editable."""
    r = await client.post(f"{BASE}/projects", json=project_payload)
    project_id = r.json()["id"]

    r2 = await client.post(f"{BASE}/projects/{project_id}/revisions", json={
        "revision_code": "R00", "revision_type": "technical"
    })
    revision_id = r2.json()["id"]

    r3 = await client.post(
        f"{BASE}/projects/{project_id}/revisions/{revision_id}/freeze",
        json={"change_summary": "Primera versión congelada", "maturity": "M2"}
    )
    assert r3.status_code == 200
    data = r3.json()
    assert data["is_frozen"] is True
    assert data["input_hash"] is not None
    assert data["maturity"] == "M2"


# ── AC-06: No se puede recongelar una revisión ya congelada — P-01 ────────────
@pytest.mark.asyncio
async def test_ac06_cannot_refreeze_revision(client, project_payload):
    """AC-06: Intentar congelar revisión ya congelada devuelve 409."""
    r = await client.post(f"{BASE}/projects", json=project_payload)
    project_id = r.json()["id"]
    r2 = await client.post(f"{BASE}/projects/{project_id}/revisions", json={
        "revision_code": "R00", "revision_type": "technical"
    })
    revision_id = r2.json()["id"]

    freeze_payload = {"change_summary": "Congelada", "maturity": "M2"}
    await client.post(f"{BASE}/projects/{project_id}/revisions/{revision_id}/freeze", json=freeze_payload)

    r3 = await client.post(
        f"{BASE}/projects/{project_id}/revisions/{revision_id}/freeze",
        json=freeze_payload
    )
    assert r3.status_code == 409


# ── AC-07: Dos congelaciones del mismo contenido → mismo hash — P-02 ──────────
@pytest.mark.asyncio
async def test_ac07_reproducible_hash(client, project_payload):
    """AC-07: Mismo contenido + misma versión motor → mismo hash (reproducibilidad P-02)."""
    r = await client.post(f"{BASE}/projects", json=project_payload)
    project_id = r.json()["id"]

    # Crear dos revisiones con contenido vacío idéntico
    hashes = []
    for code in ["R00", "R01"]:
        r2 = await client.post(f"{BASE}/projects/{project_id}/revisions", json={
            "revision_code": code, "revision_type": "technical"
        })
        rid = r2.json()["id"]
        r3 = await client.post(
            f"{BASE}/projects/{project_id}/revisions/{rid}/freeze",
            json={"change_summary": "Test", "maturity": "M1"}
        )
        hashes.append(r3.json()["input_hash"])

    # En Fase 1 el contenido es idéntico (vacío); hashes deben coincidir
    assert hashes[0] == hashes[1]


# ── AC-08: Transición de estado inválida → 422 ───────────────────────────────
@pytest.mark.asyncio
async def test_ac08_invalid_status_transition(client, project_payload):
    """AC-08: Transición de estado no permitida devuelve 422."""
    r = await client.post(f"{BASE}/projects", json=project_payload)
    project_id = r.json()["id"]

    # draft → validated no está permitido directamente
    r2 = await client.post(f"{BASE}/projects/{project_id}/status", json={
        "target_status": "validated",
        "reason": "Saltar pasos"
    })
    assert r2.status_code == 422


# ── AC-09: Solo OT puede validar M3 ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_ac09_only_ot_can_validate_m3(client, project_payload):
    """AC-09: Un ingeniero no puede validar M3; devuelve 403."""
    r = await client.post(f"{BASE}/projects", json=project_payload)
    project_id = r.json()["id"]
    r2 = await client.post(f"{BASE}/projects/{project_id}/revisions", json={
        "revision_code": "R00", "revision_type": "technical"
    })
    revision_id = r2.json()["id"]
    await client.post(
        f"{BASE}/projects/{project_id}/revisions/{revision_id}/freeze",
        json={"change_summary": "Ok", "maturity": "M2"}
    )

    # El usuario stub es ENGINEER → no puede validar M3
    r3 = await client.post(
        f"{BASE}/projects/{project_id}/revisions/{revision_id}/validate-m3",
        json={"validation_comment": "Aprobado", "accept": True}
    )
    assert r3.status_code == 403


# ── AC-10: Proyecto no encontrado → 404 sin fuga — AC-21 ─────────────────────
@pytest.mark.asyncio
async def test_ac10_project_not_found(client):
    """AC-10 / AC-21: UUID inexistente devuelve 404 sin filtrar por workspace todavía."""
    r = await client.get(f"{BASE}/projects/{uuid.uuid4()}")
    assert r.status_code == 404
    # No debe devolver metadatos del proyecto si existiera en otro workspace
    assert "id" not in r.json()


# ── AC-11: Listar proyectos con paginación ────────────────────────────────────
@pytest.mark.asyncio
async def test_ac11_list_projects_pagination(client, project_payload):
    """AC-11: Listado devuelve paginación correcta."""
    for i in range(3):
        p = dict(project_payload)
        p["name"] = f"Proyecto {i}"
        await client.post(f"{BASE}/projects", json=p)

    r = await client.get(f"{BASE}/projects?page=1&page_size=2")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "total" in data
    assert len(data["items"]) <= 2


# ── AC-12: Código de proyecto único ───────────────────────────────────────────
@pytest.mark.asyncio
async def test_ac12_unique_project_code(client, project_payload):
    """AC-12: Dos proyectos creados tienen códigos distintos."""
    r1 = await client.post(f"{BASE}/projects", json=project_payload)
    r2 = await client.post(f"{BASE}/projects", json=project_payload)
    assert r1.json()["project_code"] != r2.json()["project_code"]


# ── AC-13: Archivar proyecto ──────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_ac13_archive_project(client, project_payload):
    """AC-13: Archivar proyecto cambia estado y registra archived_at."""
    r = await client.post(f"{BASE}/projects", json=project_payload)
    project_id = r.json()["id"]

    r2 = await client.post(f"{BASE}/projects/{project_id}/archive")
    assert r2.status_code == 200
    data = r2.json()
    assert data["status"] == "archived"
    assert data["archived_at"] is not None


# ── AC-14: Filtrar proyectos por estado ───────────────────────────────────────
@pytest.mark.asyncio
async def test_ac14_filter_by_status(client, project_payload):
    """AC-14: Filtrado por estado devuelve solo proyectos con ese estado."""
    r = await client.post(f"{BASE}/projects", json=project_payload)
    project_id = r.json()["id"]
    await client.post(f"{BASE}/projects/{project_id}/archive")

    r2 = await client.get(f"{BASE}/projects?status=archived")
    items = r2.json()["items"]
    assert all(i["status"] == "archived" for i in items)


# ── AC-15: Health check disponible ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_ac15_health_check(client):
    """AC-15: El endpoint /health devuelve status ok."""
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
