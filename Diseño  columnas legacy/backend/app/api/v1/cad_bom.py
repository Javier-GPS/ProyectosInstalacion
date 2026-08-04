"""
Salvi Studio · Columns — API Fase 14
CAD paramétrico, BOM y documentación industrial
11 endpoints (todos HTTP 501 hasta milestone M1+)
"""
from uuid import UUID

from fastapi import APIRouter

from app.models.schemas.cad_bom import (
    ProductSnapshotCreate, ProductSnapshotOut,
    CadJobRequest, CadArtifactOut,
    DrawingJobRequest, DrawingArtifactOut,
    BomBuildRequest, BomHeaderOut,
    RoutingBuildRequest, RoutingOut,
    DocumentPackageRequest, DocumentPackageOut,
    ReleaseValidateRequest, ReleaseValidateOut,
    ReleaseRequest, ReleaseRecordOut,
    ChangeImpactRequest, ChangeImpactOut,
    ErpPublishRequest, ErpPublishOut,
    ArtifactManifestOut,
)

router = APIRouter(prefix="/cad-bom", tags=["cad-bom"])


@router.post(
    "/product-snapshots",
    response_model=ProductSnapshotOut,
    status_code=201,
    summary="Crear ProductSnapshot industrial",
)
async def create_product_snapshot(body: ProductSnapshotCreate):
    """
    Crea un nuevo ProductSnapshot a partir de los parámetros de diseño
    congelados. Calcula snapshot_hash determinístico.

    Requiere milestone M1 (DB activa).
    """
    raise NotImplementedError("Requiere DB — milestone M1")


@router.post(
    "/cad/jobs",
    response_model=CadArtifactOut,
    status_code=202,
    summary="Iniciar trabajo de generación CAD (STEP / DXF / GLB)",
)
async def create_cad_job(body: CadJobRequest):
    """
    Encola la generación de un artefacto CAD (STEP AP242, DXF por capas,
    GLB ligero) para el ProductSnapshot indicado.

    Requiere milestone M1.
    """
    raise NotImplementedError("Requiere DB — milestone M1")


@router.get(
    "/cad/jobs/{job_id}",
    response_model=CadArtifactOut,
    summary="Consultar estado de trabajo CAD",
)
async def get_cad_job(job_id: UUID):
    """
    Consulta el estado y resultado de un trabajo CAD previamente encolado.

    Requiere milestone M1.
    """
    raise NotImplementedError("Requiere DB — milestone M1")


@router.post(
    "/drawings/jobs",
    response_model=DrawingArtifactOut,
    status_code=202,
    summary="Generar plano 2D",
)
async def create_drawing_job(body: DrawingJobRequest):
    """
    Genera el plano 2D (PDF) para el ProductSnapshot: selecciona vistas,
    valida completitud de cajetín y densidad de cotas.

    Requiere milestone M1.
    """
    raise NotImplementedError("Requiere DB — milestone M1")


@router.post(
    "/boms/build",
    response_model=BomHeaderOut,
    status_code=201,
    summary="Construir BOM (EBOM / MBOM / PBOM / SBOM)",
)
async def build_bom(body: BomBuildRequest):
    """
    Construye la BOM de la vista solicitada y reconcilia masa CAD vs BOM
    (umbral ≤ 0,5 %).

    Requiere milestone M1.
    """
    raise NotImplementedError("Requiere DB — milestone M1")


@router.post(
    "/routings/build",
    response_model=RoutingOut,
    status_code=201,
    summary="Generar ruta de fabricación",
)
async def build_routing(body: RoutingBuildRequest):
    """
    Genera la ruta de fabricación con operaciones en secuencia normalizada
    para el material del ProductSnapshot.

    Requiere milestone M1.
    """
    raise NotImplementedError("Requiere DB — milestone M1")


@router.post(
    "/documents/packages",
    response_model=DocumentPackageOut,
    status_code=201,
    summary="Crear paquete documental por audiencia",
)
async def create_document_package(body: DocumentPackageRequest):
    """
    Genera el paquete de documentos apropiado para la audiencia y el idioma
    indicados (CLIENT, ENGINEERING, PRODUCTION, QUALITY, SUPPLIER, SITE,
    REGULATORY).

    Requiere milestone M1.
    """
    raise NotImplementedError("Requiere DB — milestone M1")


@router.post(
    "/releases/validate",
    response_model=ReleaseValidateOut,
    summary="Validar puertas de liberación",
)
async def validate_release(body: ReleaseValidateRequest):
    """
    Evalúa las 6 puertas de liberación (CAD_VALID, DRAWING_VALID,
    BOM_RECONCILED, ROUTING_COMPLETE, INSPECTION_PLAN, DOCUMENT_PACKAGE)
    y devuelve lista de bloqueantes.

    Requiere milestone M1.
    """
    raise NotImplementedError("Requiere DB — milestone M1")


@router.post(
    "/releases",
    response_model=ReleaseRecordOut,
    status_code=201,
    summary="Liberar ProductSnapshot y publicar en ERP/PDM",
)
async def release_snapshot(body: ReleaseRequest):
    """
    Crea el ReleaseRecord, transiciona el ProductSnapshot a RELEASED
    y publica en ERP/PDM/PLM. Requiere que todas las puertas estén en PASSED
    o WAIVED.

    Requiere milestone M1.
    """
    raise NotImplementedError("Requiere DB — milestone M1")


@router.post(
    "/changes/impact",
    response_model=ChangeImpactOut,
    summary="Calcular impacto de cambio sobre artefactos",
)
async def evaluate_change_impact(body: ChangeImpactRequest):
    """
    Calcula qué artefactos y documentos quedan invalidados por una propuesta
    de cambio según su clase (EDITORIAL / INDUSTRIAL / GEOMETRIC / STRUCTURAL
    / REGULATORY) y estima el esfuerzo de actualización.

    Requiere milestone M1.
    """
    raise NotImplementedError("Requiere DB — milestone M1")


@router.post(
    "/integrations/erp/publish",
    response_model=ErpPublishOut,
    summary="Publicar en ERP",
)
async def publish_to_erp(body: ErpPublishRequest):
    """
    Publica BOM y ruta en el sistema ERP objetivo para el ReleaseRecord
    indicado. Soporta modo `dry_run`.

    Requiere milestone M1.
    """
    raise NotImplementedError("Requiere DB — milestone M1")
