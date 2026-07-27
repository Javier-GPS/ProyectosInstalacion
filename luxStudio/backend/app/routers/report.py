import io
import json
import traceback
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from pypdf import PdfReader, PdfWriter
from sqlalchemy.orm import Session

from ..database import engine, get_db
from ..models import Project, Tramo, TramoDocument
from ..schemas.models import CalculationConfig, CalculationResult, MeasurementGrid, MeasurementResponse
from ..services.calculator import run_calculation
from ..services.excel_generator import generate_excel, generate_multi_excel
from ..services.ldt_matcher import require_ldt_for_config
from ..services.pdf_generator import generate_pdf
from ..services.report_grids import calculation_grids
from ._access import can_access_project
from .deps import current_user

router = APIRouter()


def _measurement_grid_payload(grid: dict) -> MeasurementGrid:
    avg = float(grid.get("avg") or 0)
    min_value = float(grid.get("min") or 0)
    max_value = float(grid.get("max") or 0)
    return MeasurementGrid(
        title=str(grid.get("title") or ""),
        unit=str(grid.get("unit") or ""),
        xs=[float(value) for value in grid.get("xs", [])],
        ys=[float(value) for value in grid.get("ys", [])],
        values=[
            [float(value) for value in column]
            for column in grid.get("values", [])
        ],
        avg=avg,
        min=min_value,
        max=max_value,
        uniformity_avg=(min_value / avg) if avg > 0 else 0,
        uniformity_max=(min_value / max_value) if max_value > 0 else 0,
    )


def _ensure_document_tables() -> None:
    Project.__table__.create(bind=engine, checkfirst=True)
    Tramo.__table__.create(bind=engine, checkfirst=True)
    TramoDocument.__table__.create(bind=engine, checkfirst=True)


def _safe_filename(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in value).strip("_")


def _store_tramo_document(
    db: Session,
    tramo_id: Optional[int],
    filename: str,
    document_type: str,
    content_type: str,
    data: bytes,
) -> None:
    if not tramo_id:
        return
    _ensure_document_tables()
    db.query(TramoDocument).filter(
        TramoDocument.tramo_id == tramo_id,
        TramoDocument.document_type == document_type,
    ).delete()
    db.add(TramoDocument(
        tramo_id=tramo_id,
        filename=filename,
        document_type=document_type,
        content_type=content_type,
        data=data,
    ))
    db.commit()


def _project_payload(project: Optional[Project], tramo: Optional[Tramo] = None) -> Optional[dict]:
    if not project:
        return None
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    project_name = project.project_name
    if tramo:
        project_name = f"{project.project_name} - {tramo.name}"
    return {
        "project_name": project_name,
        "client": project.client,
        "location": project.location,
        "designer": project.designer,
        "study_date": now,
        "reference": project.reference,
        "calculation_type": project.calculation_type,
        "standard": project.standard,
        "notes": project.notes,
    }


def _resolve_tramo_and_project(
    db: Session,
    tramo_id: Optional[int],
    project_id: Optional[int],
    user,
) -> tuple[Optional[Tramo], Optional[Project]]:
    tramo: Optional[Tramo] = None
    project: Optional[Project] = None
    if tramo_id is not None:
        tramo = db.get(Tramo, tramo_id)
        if not tramo:
            raise HTTPException(status_code=404, detail="Tramo not found")
        project = db.get(Project, tramo.project_id)
        if not project or not can_access_project(project, user):
            raise HTTPException(status_code=404, detail="Tramo not found")
    elif project_id is not None:
        project = db.get(Project, project_id)
        if not project or not can_access_project(project, user):
            raise HTTPException(status_code=404, detail="Project not found")
    return tramo, project


def _stored_result(tramo: Optional[Tramo]) -> Optional[CalculationResult]:
    if not tramo or not tramo.result_json:
        return None
    try:
        data = json.loads(tramo.result_json)
        data.pop("__status", None)
        data.pop("__configHash", None)
        return CalculationResult.model_validate(data)
    except Exception:
        return None


@router.post("/generate")
async def generate_report(
    config: CalculationConfig,
    project_id: Optional[int] = Query(default=None),
    tramo_id: Optional[int] = Query(default=None),
    user=Depends(current_user),
    db: Session = Depends(get_db),
):
    """Generate a professional PDF report for the given configuration."""
    try:
        tramo, project = _resolve_tramo_and_project(db, tramo_id, project_id, user)
        result = _stored_result(tramo)
        if result is None:
            ldt_id, ldt = require_ldt_for_config(config)
            result = run_calculation(config, ldt_id)
        pdf_bytes = await generate_pdf(result, _project_payload(project, tramo))
        if tramo:
            filename_prefix = _safe_filename(f"{project.project_name}_{tramo.name}" if project else tramo.name)
        elif project:
            filename_prefix = _safe_filename(project.project_name)
        else:
            filename_prefix = _safe_filename(ldt["luminaire_name"])
        filename = f"LUX_Report_{filename_prefix}.pdf"
        _store_tramo_document(db, tramo_id, filename, "pdf", "application/pdf", pdf_bytes)

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            },
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generating PDF report: {str(e)}")


@router.post("/excel")
async def generate_excel_report(
    config: CalculationConfig,
    project_id: Optional[int] = Query(default=None),
    tramo_id: Optional[int] = Query(default=None),
    user=Depends(current_user),
    db: Session = Depends(get_db),
):
    """Generate a DIALux-style Excel output for the given configuration."""
    try:
        tramo, project = _resolve_tramo_and_project(db, tramo_id, project_id, user)
        result = _stored_result(tramo)
        if result is None:
            ldt_id, ldt = require_ldt_for_config(config)
            result = run_calculation(config, ldt_id)
        excel_bytes = generate_excel(result, _project_payload(project, tramo), tramo_name=tramo.name if tramo else "MODELO 1")
        if tramo:
            filename_prefix = _safe_filename(f"{project.project_name}_{tramo.name}" if project else tramo.name)
        elif project:
            filename_prefix = _safe_filename(project.project_name)
        else:
            filename_prefix = _safe_filename(ldt["luminaire_name"])
        filename = f"LUX_Results_{filename_prefix}.xlsx"
        _store_tramo_document(
            db,
            tramo_id,
            filename,
            "excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            excel_bytes,
        )

        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            },
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generating Excel report: {str(e)}")


class BulkExcelRequest(BaseModel):
    tramo_ids: list[int] = Field(..., min_length=1, max_length=2000)


@router.post("/excel-batch")
async def generate_batch_excel_report(
    body: BulkExcelRequest,
    user=Depends(current_user),
    db: Session = Depends(get_db),
):
    """Generate a multi-row Excel with one row per tramo."""
    try:
        project = None
        results: list[CalculationResult] = []
        tramo_names: list[str] = []

        for tramo_id in body.tramo_ids:
            tramo = db.get(Tramo, tramo_id)
            if not tramo:
                raise HTTPException(status_code=404, detail=f"Tramo {tramo_id} not found")
            if project is None:
                project = db.get(Project, tramo.project_id)
                if not project or not can_access_project(project, user):
                    raise HTTPException(status_code=404, detail="Project not found")
            elif tramo.project_id != project.id:
                raise HTTPException(status_code=400, detail="All tramos must belong to the same project")

            result = _stored_result(tramo)
            if result is None:
                raise HTTPException(status_code=400, detail=f"Tramo {tramo_id} has no stored result. Calculate it first.")
            results.append(result)
            tramo_names.append(tramo.name)

        if not results:
            raise HTTPException(status_code=400, detail="No valid tramos with results found")

        excel_bytes = generate_multi_excel(results, _project_payload(project), tramo_names=tramo_names)
        filename = f"LUX_Results_{_safe_filename(project.project_name)}.xlsx" if project else "LUX_Results.xlsx"

        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generating batch Excel: {str(e)}")


@router.post("/pdf-batch")
async def generate_batch_pdf_report(
    body: BulkExcelRequest,
    user=Depends(current_user),
    db: Session = Depends(get_db),
):
    """Generate a single PDF merging one report per tramo."""
    try:
        project = None
        pdfs_bytes: list[bytes] = []

        for tramo_id in body.tramo_ids:
            tramo = db.get(Tramo, tramo_id)
            if not tramo:
                raise HTTPException(status_code=404, detail=f"Tramo {tramo_id} not found")
            if project is None:
                project = db.get(Project, tramo.project_id)
                if not project or not can_access_project(project, user):
                    raise HTTPException(status_code=404, detail="Project not found")
            elif tramo.project_id != project.id:
                raise HTTPException(status_code=400, detail="All tramos must belong to the same project")

            result = _stored_result(tramo)
            if result is None:
                raise HTTPException(status_code=400, detail=f"Tramo {tramo_id} has no stored result. Calculate it first.")

            pdf_bytes = await generate_pdf(result, _project_payload(project, tramo))
            pdfs_bytes.append(pdf_bytes)

        if not pdfs_bytes:
            raise HTTPException(status_code=400, detail="No valid tramos with results found")

        writer = PdfWriter()
        for pdf_bytes in pdfs_bytes:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            writer.append(reader)

        buf = io.BytesIO()
        writer.write(buf)
        merged = buf.getvalue()

        filename = f"LUX_Report_{_safe_filename(project.project_name)}.pdf" if project else "LUX_Report.pdf"
        return Response(
            content=merged,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generating batch PDF: {str(e)}")


@router.post("/measurements", response_model=MeasurementResponse)
async def get_measurements(
    config: CalculationConfig,
    user=Depends(current_user),
):
    """Return the calculated point matrix used for report checking."""
    try:
        ldt_id, _ldt = require_ldt_for_config(config)
        result = run_calculation(config, ldt_id)
        grids = calculation_grids(result, ldt_id)
        payload = {
            key: _measurement_grid_payload(grid)
            for key, grid in grids.items()
        }
        if not payload:
            raise ValueError("No calculation grid is available")
        primary = "illuminance" if "illuminance" in payload else next(iter(payload))
        return MeasurementResponse(
            config=result.config,
            luminaire=result.luminaire,
            primary=primary,
            grids=payload,
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generating measurements: {str(e)}")
