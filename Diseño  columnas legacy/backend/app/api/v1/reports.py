"""
Salvi Studio · Columns — Router API Fase 15
Informes, Validación Documental y Liberación.
Todos los endpoints devuelven HTTP 501 hasta el milestone M1 (implementación con DB).
"""
import uuid
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/reports", tags=["reports"])

_NOT_IMPLEMENTED = JSONResponse(
    status_code=501,
    content={"detail": "Requiere conexión a base de datos — milestone M1."},
)


@router.post("/releases", status_code=201, summary="Crear release snapshot")
async def create_release():
    """
    Crea un nuevo ReleaseSnapshot en estado DRAFT (M0).
    Captura hashes de snapshots de fases 1-14.
    """
    return _NOT_IMPLEMENTED


@router.post("/releases/{release_id}/validate", summary="Ejecutar validación automática")
async def validate_release(release_id: uuid.UUID):
    """
    Ejecuta la suite de validación automática para el gate indicado.
    Produce un ValidationRun con checks REL-* tipificados.
    """
    return _NOT_IMPLEMENTED


@router.post("/releases/{release_id}/documents", status_code=201, summary="Componer documento")
async def compose_document(release_id: uuid.UUID):
    """
    Compone una instancia de documento a partir de una plantilla aprobada.
    El documento es una vista del expediente, nunca una fuente primaria.
    """
    return _NOT_IMPLEMENTED


@router.post("/releases/{release_id}/reviews", status_code=201, summary="Abrir revisión OT")
async def create_review(release_id: uuid.UUID):
    """
    Abre una tarea de revisión de Oficina Técnica (regla cuatro ojos).
    El revisor no puede ser el mismo que el solicitante.
    """
    return _NOT_IMPLEMENTED


@router.post("/reviews/{review_id}/decision", summary="Registrar decisión de revisión")
async def record_review_decision(review_id: uuid.UUID):
    """
    Registra la decisión del revisor OT (APPROVED / REJECTED / REQUESTED_CHANGES).
    Solo el revisor asignado puede decidir.
    """
    return _NOT_IMPLEMENTED


@router.post("/releases/{release_id}/approve", status_code=201, summary="Registrar aprobación formal")
async def approve_release(release_id: uuid.UUID):
    """
    Registra una aprobación formal con nivel de autenticación (A1/A2/A3).
    Implementa la regla de cuatro ojos: aprobador ≠ revisor.
    """
    return _NOT_IMPLEMENTED


@router.post("/releases/{release_id}/publish", summary="Publicar release (M4)")
async def publish_release(release_id: uuid.UUID):
    """
    Publica el release con firma del manifiesto (auth_level >= A2).
    Avanza el estado a LIBERADO. Requiere G4 aprobado.
    """
    return _NOT_IMPLEMENTED


@router.post("/releases/{release_id}/revoke", summary="Revocar release")
async def revoke_release(release_id: uuid.UUID):
    """
    Revoca un release en estado VALIDADO_OT o LIBERADO.
    Notifica a todos los receptores de la versión revocada.
    Bloquea nuevas descargas sin borrar el histórico.
    """
    return _NOT_IMPLEMENTED


@router.get("/releases/{release_id}/manifest", summary="Obtener manifiesto del expediente")
async def get_manifest(release_id: uuid.UUID):
    """
    Devuelve el manifiesto inmutable del release.
    Incluye hashes de todos los artefactos, aprobaciones y distribuciones.
    """
    return _NOT_IMPLEMENTED


@router.get("/releases/{release_id}/diff/{other_id}", summary="Diff semántico entre revisiones")
async def get_diff(release_id: uuid.UUID, other_id: uuid.UUID):
    """
    Compara semánticamente dos revisiones del expediente.
    Clasifica cada cambio por naturaleza (ENTRADA_TECNICA, EDITORIAL, etc.),
    criticidad y artefactos afectados.
    """
    return _NOT_IMPLEMENTED
