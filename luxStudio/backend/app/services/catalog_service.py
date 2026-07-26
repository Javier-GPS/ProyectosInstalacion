"""CRUD operations for catalog dimension tables.

This service provides create / update / delete operations for the four
dimension tables (``gamas``, ``difusores``, ``lentes``, ``led_types``)
and for the ``valid_combinations`` junction table.

All operations are idempotent: creating a row that already exists raises
``ValueError`` with a descriptive message.  Deleting a row that is still
referenced by ``luminaires`` raises ``ValueError`` (RESTRICT on FK);
deleting one referenced only by ``valid_combinations`` cascades.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.text_utils import norm as _norm
from ..models.catalog import Difusor, Gama, LedType, Lente, ValidCombination
from ..models.luminaire import Fotometria
from ..models.luminaire_catalog import Driver, LED, PCB, LuminaireLED


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DIMENSION_MODELS = {
    "gama": Gama,
    "difusor": Difusor,
    "lente": Lente,
    "led_type": LedType,
}

FK_TO_LUMINAIRE = {
        "gama": Fotometria.gama_id,
        "difusor": Fotometria.difusor_id,
        "lente": Fotometria.lente_id,
        "led_type": Fotometria.led_type_id,
}


def get_eficiencia(db: Session, lente: str | None = None, difusor: str | None = None) -> tuple[float, float]:
    lente_eff = db.query(Lente.eficiencia).filter(Lente.name == (lente or "")).scalar() if lente else None
    difusor_eff = db.query(Difusor.eficiencia).filter(Difusor.name == (difusor or "")).scalar() if difusor else None
    return (lente_eff or 1.0, difusor_eff or 1.0)


def _get_or_404(db: Session, model, item_id: int):
    obj = db.query(model).get(item_id)
    if obj is None:
        raise ValueError(f"{model.__name__} {item_id} not found")
    return obj


# ---------------------------------------------------------------------------
# Generic dimension CRUD
# ---------------------------------------------------------------------------

def list_items(db: Session, dimension: str) -> list[dict]:
    model = _DIMENSION_MODELS[dimension]
    rows = db.query(model).order_by(model.name).all()
    if dimension == "difusor":
        return [{"id": r.id, "name": r.name, "eficiencia": getattr(r, "eficiencia", None)} for r in rows]
    if dimension == "lente":
        return [{"id": r.id, "name": r.name, "eficiencia": getattr(r, "eficiencia", None)} for r in rows]
    return [{"id": r.id, "name": r.name} for r in rows]


def create_item(db: Session, dimension: str, name: str) -> dict:
    model = _DIMENSION_MODELS[dimension]
    name = name.strip().upper()
    if not name:
        raise ValueError("Name cannot be empty")
    existing = db.query(model).filter(model.name == name).first()
    if existing is not None:
        raise ValueError(f"A {dimension} with name '{name}' already exists (id={existing.id})")
    obj = model(name=name)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return {"id": obj.id, "name": obj.name}


def update_item(db: Session, dimension: str, item_id: int, name: str) -> dict:
    model = _DIMENSION_MODELS[dimension]
    obj = _get_or_404(db, model, item_id)
    name = name.strip().upper()
    if not name:
        raise ValueError("Name cannot be empty")
    conflict = db.query(model).filter(model.name == name, model.id != item_id).first()
    if conflict is not None:
        raise ValueError(f"A {dimension} with name '{name}' already exists (id={conflict.id})")
    obj.name = name
    db.commit()
    db.refresh(obj)
    return {"id": obj.id, "name": obj.name}


def delete_item(db: Session, dimension: str, item_id: int) -> None:
    model = _DIMENSION_MODELS[dimension]
    obj = _get_or_404(db, model, item_id)
    # Check if any luminaires reference this dimension.
    fk_col = FK_TO_LUMINAIRE[dimension]
    count = db.query(func.count(Fotometria.id)).filter(fk_col == item_id).scalar()
    if count > 0:
        raise ValueError(
            f"Cannot delete {dimension} '{obj.name}': "
            f"{count} luminaire(s) still reference it."
        )
    db.delete(obj)
    db.commit()


# ---------------------------------------------------------------------------
# Valid combinations
# ---------------------------------------------------------------------------

def list_valid_combinations(db: Session) -> list[dict]:
    rows = (
        db.query(ValidCombination)
        .order_by(ValidCombination.id)
        .all()
    )
    return [
        {
            "id": r.id,
            "gama": r.gama.name if r.gama else None,
            "gama_id": r.gama_id,
            "difusor": r.difusor.name if r.difusor else None,
            "difusor_id": r.difusor_id,
            "lente": r.lente.name if r.lente else None,
            "lente_id": r.lente_id,
            "led_type": r.led_type.name if r.led_type else None,
            "led_type_id": r.led_type_id,
        }
        for r in rows
    ]


def create_valid_combination(
    db: Session,
    gama_id: int,
    difusor_id: int,
    lente_id: int,
    led_type_id: int | None = None,
) -> dict:
    # Validate FKs exist.
    _get_or_404(db, Gama, gama_id)
    _get_or_404(db, Difusor, difusor_id)
    _get_or_404(db, Lente, lente_id)
    if led_type_id is not None:
        _get_or_404(db, LedType, led_type_id)

    existing = (
        db.query(ValidCombination)
        .filter(
            ValidCombination.gama_id == gama_id,
            ValidCombination.difusor_id == difusor_id,
            ValidCombination.lente_id == lente_id,
            ValidCombination.led_type_id == led_type_id,
        )
        .first()
    )
    if existing is not None:
        raise ValueError(
            f"Combination already exists (id={existing.id})"
        )
    vc = ValidCombination(
        gama_id=gama_id,
        difusor_id=difusor_id,
        lente_id=lente_id,
        led_type_id=led_type_id,
    )
    db.add(vc)
    db.commit()
    db.refresh(vc)
    return {
        "id": vc.id,
        "gama": vc.gama.name,
        "gama_id": vc.gama_id,
        "difusor": vc.difusor.name,
        "difusor_id": vc.difusor_id,
        "lente": vc.lente.name,
        "lente_id": vc.lente_id,
        "led_type": vc.led_type.name if vc.led_type else None,
        "led_type_id": vc.led_type_id,
    }


# ---------------------------------------------------------------------------
# Catalog tables (LED, PCB, Driver, LuminaireLED) — read-only
# ---------------------------------------------------------------------------


def list_leds(db: Session) -> list[dict]:
    rows = db.query(LED).order_by(LED.led_ref).all()
    return [
        {
            "id": r.id,
            "led_ref": r.led_ref,
            "led_desc_corta": r.led_desc_corta,
            "led_tipo": r.led_tipo,
            "pmax_lum": r.pmax_lum,
            "i_max_led": r.i_max_led,
            "pmax_ajustada": r.pmax_ajustada,
        }
        for r in rows
    ]


def list_pcbs(db: Session) -> list[dict]:
    rows = db.query(PCB).order_by(PCB.pcb_ref).all()
    return [
        {
            "id": r.id,
            "pcb_ref": r.pcb_ref,
            "pcb_descripcion": r.pcb_descripcion,
            "pcb_no_drivers": r.pcb_no_drivers,
            "pcb_v_nominal": r.pcb_v_nominal,
            "pcb_no_led": r.pcb_no_led,
            "pcb_no_circuitos": r.pcb_no_circuitos,
            "pcb_imax_led": r.pcb_imax_led,
        }
        for r in rows
    ]


def create_pcb(db: Session, data: dict) -> dict:
    ref = data["pcb_ref"]
    instance = db.query(PCB).filter(PCB.pcb_ref == ref).first()
    if instance is None:
        instance = PCB(pcb_ref=ref)
        db.add(instance)
    for field in ("pcb_descripcion", "pcb_no_drivers", "pcb_v_nominal", "pcb_no_led", "pcb_no_circuitos", "pcb_imax_led"):
        val = data.get(field)
        if val is not None:
            setattr(instance, field, val)
    db.commit()
    db.refresh(instance)
    return {
        "id": instance.id,
        "pcb_ref": instance.pcb_ref,
        "pcb_descripcion": instance.pcb_descripcion,
        "pcb_no_drivers": instance.pcb_no_drivers,
        "pcb_v_nominal": instance.pcb_v_nominal,
        "pcb_no_led": instance.pcb_no_led,
        "pcb_no_circuitos": instance.pcb_no_circuitos,
        "pcb_imax_led": instance.pcb_imax_led,
    }


def list_drivers(db: Session) -> list[dict]:
    rows = db.query(Driver).order_by(Driver.dr_ref).all()
    return [
        {
            "id": r.id,
            "dr_ref": r.dr_ref,
            "dr_pot_max_driver": r.dr_pot_max_driver,
        }
        for r in rows
    ]


def list_luminaire_leds(db: Session) -> list[dict]:
    rows = (
        db.query(LuminaireLED)
        .order_by(LuminaireLED.id)
        .all()
    )
    return [
        {
            "id": r.id,
            "gama": r.gama.name if r.gama else None,
            "difusor": r.difusor.name if r.difusor else None,
            "lente": r.lente.name if r.lente else None,
            "led_type": r.led_type.name if r.led_type else None,
            "led_ref": r.led.led_ref if r.led else None,
            "pmax_ajustada": r.led.pmax_ajustada if r.led else None,
            "led_tipo": r.led.led_tipo if r.led else None,
            "pcb_ref": r.pcb.pcb_ref if r.pcb else None,
            "n_pcbs": r.n_pcbs,
            "n_leds_per_pcb": r.n_leds_per_pcb,
        }
        for r in rows
    ]


def create_luminaire_led(
    db: Session,
    gama: str,
    difusor: str,
    lente: str,
    led_ref: str,
    led_type: str | None = None,
    pcb_ref: str | None = None,
    n_pcbs: int | None = None,
    n_leds_per_pcb: int | None = None,
) -> dict:
    gama_row = db.query(Gama).filter(Gama.name == _norm(gama)).first()
    if gama_row is None:
        raise ValueError(f"Gama '{gama}' not found")

    difusor_row = db.query(Difusor).filter(Difusor.name == _norm(difusor)).first()
    if difusor_row is None:
        raise ValueError(f"Difusor '{difusor}' not found")

    lente_row = db.query(Lente).filter(Lente.name == _norm(lente)).first()
    if lente_row is None:
        raise ValueError(f"Lente '{lente}' not found")

    led_row = db.query(LED).filter(LED.led_ref == _norm(led_ref)).first()
    if led_row is None:
        raise ValueError(f"LED '{led_ref}' not found")

    led_type_id = None
    if led_type:
        lt_row = db.query(LedType).filter(LedType.name == _norm(led_type)).first()
        if lt_row is None:
            raise ValueError(f"LedType '{led_type}' not found")
        led_type_id = lt_row.id

    pcb_id = None
    if pcb_ref:
        pcb_row = db.query(PCB).filter(PCB.pcb_ref == _norm(pcb_ref)).first()
        if pcb_row is None:
            raise ValueError(f"PCB '{pcb_ref}' not found")
        pcb_id = pcb_row.id

    existing = (
        db.query(LuminaireLED)
        .filter(
            LuminaireLED.gama_id == gama_row.id,
            LuminaireLED.difusor_id == difusor_row.id,
            LuminaireLED.lente_id == lente_row.id,
            LuminaireLED.led_type_id == led_type_id,
        )
        .first()
    )
    if existing:
        raise ValueError(
            f"4-tuple already exists (id={existing.id}): "
            f"{_norm(gama)}/{_norm(difusor)}/{_norm(lente)}/{led_type or '—'}"
        )

    entry = LuminaireLED(
        gama_id=gama_row.id,
        difusor_id=difusor_row.id,
        lente_id=lente_row.id,
        led_type_id=led_type_id,
        led_id=led_row.id,
        pcb_id=pcb_id,
        n_pcbs=n_pcbs,
        n_leds_per_pcb=n_leds_per_pcb,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    return {
        "id": entry.id,
        "gama": entry.gama.name,
        "difusor": entry.difusor.name,
        "lente": entry.lente.name,
        "led_type": entry.led_type.name if entry.led_type else None,
        "led_ref": entry.led.led_ref,
        "pmax_ajustada": entry.led.pmax_ajustada,
        "led_tipo": entry.led.led_tipo,
        "pcb_ref": entry.pcb.pcb_ref if entry.pcb else None,
        "n_pcbs": entry.n_pcbs,
        "n_leds_per_pcb": entry.n_leds_per_pcb,
    }


def delete_valid_combination(db: Session, vc_id: int) -> None:
    vc = db.query(ValidCombination).get(vc_id)
    if vc is None:
        raise ValueError(f"ValidCombination {vc_id} not found")
    db.delete(vc)
    db.commit()
