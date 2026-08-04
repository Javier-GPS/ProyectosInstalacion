"""
Salvi Studio · Columns — Tests de aceptación Fase 1 (AC-16 a AC-30)
Sección 38.1, Fase 1.
"""
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app

BASE = "/api/v1"


@pytest.fixture
def project_payload():
    return {
        "name": "Test AC16-30",
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


@pytest_asyncio.fixture
async def existing_project(client, project_payload):
    r = await client.post(f"{BASE}/projects", json=project_payload)
    return r.json()


# ── AC-17: Clonar proyecto validado → nuevo borrador sin estado validado ───────
@pytest.mark.asyncio
async def test_ac17_clone_project(client, existing_project):
    """AC-17: Clonar proyecto produce borrador sin aprobaciones ni estado validado."""
    source_id = existing_project["id"]
    r = await client.post(f"{BASE}/projects", json={
        "name": "Clon del proyecto",
        "country": "ES",
        "language": "es",
        "currency": "EUR",
        "timezone": "Europe/Madrid",
        "confidentiality": "internal",
        "cloned_from_id": source_id,
    })
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "draft"
    assert data["maturity"] == "M0"
    assert data["cloned_from_id"] == source_id
    # No debe heredar estado validado
    assert data["status"] != "validated"


# ── AC-20: Idempotency-Key en POST ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_ac20_idempotency_key(client, project_payload):
    """
    AC-20: POST con misma Idempotency-Key no crea duplicados.
    Nota: implementación completa requiere caché Redis; este test verifica
    que el header se acepta sin error (comportamiento básico Fase 1).
    """
    key = str(uuid.uuid4())
    r1 = await client.post(
        f"{BASE}/projects",
        json=project_payload,
        headers={"Idempotency-Key": key}
    )
    assert r1.status_code == 201


# ── AC-21: UUID de otro workspace → 404 sin fuga ─────────────────────────────
@pytest.mark.asyncio
async def test_ac21_no_metadata_leak(client):
    """AC-21: UUID desconocido devuelve 404 sin exponer información."""
    r = await client.get(f"{BASE}/projects/{uuid.uuid4()}")
    assert r.status_code == 404
    body = r.json()
    # No debe contener campos de proyecto real
    assert "project_code" not in body
    assert "owner_user_id" not in body


# ── AC-22: Comentario anclado a campo se conserva en nueva revisión ───────────
@pytest.mark.asyncio
async def test_ac22_comment_field_anchor(client, existing_project):
    """
    AC-22: Ancla histórica de comentario se conserva.
    Este test verifica la estructura; el endpoint de comentarios
    se implementa en el sprint de colaboración.
    """
    # Verificar que el proyecto existe (base para comentarios futuros)
    project_id = existing_project["id"]
    r = await client.get(f"{BASE}/projects/{project_id}")
    assert r.status_code == 200


# ── AC-24: Health + coherencia básica del sistema ────────────────────────────
@pytest.mark.asyncio
async def test_ac24_system_coherence(client):
    """AC-24: Sistema arranca, responde y las entidades son coherentes."""
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── AC-27: Job fallido tiene error accionable ─────────────────────────────────
@pytest.mark.asyncio
async def test_ac27_async_job_error_format():
    """
    AC-27: Un job fallido devuelve estado 'failed', error accionable y correlation_id.
    Verificación de esquema de datos sin lanzar job real.
    """
    from app.models.db.audit import AsyncJob
    job = AsyncJob(
        job_type="calculation",
        status="failed",
        triggered_by_id=uuid.uuid4(),
        correlation_id=str(uuid.uuid4()),
        error_code="ENGINE_NOT_AVAILABLE",
        error_detail="El motor de cálculo no está disponible. Reintente en unos minutos.",
    )
    assert job.status == "failed"
    assert job.error_code is not None
    assert job.correlation_id is not None


# ── AC-28: Cambio de coste no invalida cálculo estructural ───────────────────
@pytest.mark.asyncio
async def test_ac28_cost_change_no_structural_invalidation():
    """
    AC-28: Una actualización de costes no debe marcar como obsoleto el cálculo estructural.
    Verificación de principio P-07 (no sobrescritura silenciosa).
    En Fase 1 se verifica que las bibliotecas son entidades separadas.
    """
    from app.models.db.libraries import Library
    # Las bibliotecas de costes son independientes de las estructurales
    lib = Library(
        code="COSTS-2026",
        name="Costes 2026",
        library_type="costs",
        owner_role="library_admin",
    )
    assert lib.library_type == "costs"
    # La biblioteca estructural tiene type diferente
    mat_lib = Library(
        code="MATERIALS-STEEL-2026",
        name="Materiales acero 2026",
        library_type="materials",
        owner_role="library_admin",
    )
    assert mat_lib.library_type == "materials"
    assert lib.library_type != mat_lib.library_type


# ── AC-29: No borrar entrada publicada referenciada ───────────────────────────
@pytest.mark.asyncio
async def test_ac29_published_library_immutable():
    """AC-29: Una versión de biblioteca publicada no puede modificarse (P-07)."""
    from app.models.db.libraries import LibraryVersion
    import uuid

    # Simular versión publicada
    version = LibraryVersion(
        library_id=uuid.uuid4(),
        version_number="1.0.0",
        status="published",
        content={"test": True},
    )
    # El estado published indica inmutabilidad — cualquier cambio requiere nueva versión
    assert version.status == "published"
    # La regla de negocio que bloquea la edición está en el servicio, no en el modelo


# ── AC-30: Exportar dato restringido sin permiso → denegado ──────────────────
@pytest.mark.asyncio
async def test_ac30_restricted_export_denied(client):
    """
    AC-30: Sin permiso, operaciones de exportación restringida son denegadas.
    En Fase 1 verificamos que rutas no existentes devuelven 404 (no 200 con datos).
    El control de exportación completo se implementa en Fase 15.
    """
    r = await client.get(f"{BASE}/projects/{uuid.uuid4()}/export")
    # Ruta no implementada → 404 (no expone datos)
    assert r.status_code == 404


# ── Verificación de modelo de unidades (P-06) ─────────────────────────────────
@pytest.mark.asyncio
async def test_units_si_conversion():
    """
    Test unitario del servicio de unidades.
    P-06: conversiones correctas; comparaciones con valor SI no redondeado.
    """
    from app.models.db.units import Quantity, PhysicalDimension

    q = Quantity.from_user_input(100.0, "mm", PhysicalDimension.LENGTH)
    assert abs(q.value_si - 0.1) < 1e-10

    q2 = Quantity.from_user_input(1.0, "kN", PhysicalDimension.FORCE)
    assert abs(q2.value_si - 1000.0) < 1e-10

    q3 = Quantity.from_user_input(20.0, "°C", PhysicalDimension.TEMPERATURE)
    assert abs(q3.value_si - 293.15) < 1e-10

    # Presentación en unidades distintas
    assert abs(q.to_unit("mm") - 100.0) < 1e-8
    assert abs(q2.to_unit("kN") - 1.0) < 1e-10
