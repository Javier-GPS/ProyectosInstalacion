from __future__ import annotations

import json
from types import SimpleNamespace

from sqlalchemy.orm import sessionmaker

from conftest import create_test_engine

from app.database import Base
from app.models import Project, Tramo
from app.models.catalog import Difusor, Gama, Lente, LedType
from app.routers.tramos import _build_status_context, _compliance_summary, _tramo_status
from app.schemas.models import CalculationConfig
from app.services import tramo_operations


def _base_config(**overrides) -> dict:
    base = {
        "road_width": 7.0,
        "sidewalk_left": 1.5,
        "sidewalk_right": 1.5,
        "lanes": 2,
        "arrangement": "Lineal",
        "height": 9.0,
        "spacing": 30.0,
        "arm_length": 1.5,
        "pole_offset": 0.0,
        "pole_side": "left",
        "tilt": 5.0,
        "optic_family": "F151",
        "target_flux": 10000.0,
        "power": 80.0,
        "ldt_id": "ldt-1",
        "manufacturer": "SALVI",
        "model_family": "ATENEA",
        "gama": "ATENEA",
        "difusor": "PMMA LC",
        "lente": "F151",
        "led_type": "LUXEON HOP 5050",
        "lighting_class": "M3",
        "mf": 0.85,
        "pavement": "R3",
        "cct": 4000,
        "cri": 70,
        "language": "es",
        "driver_eficiencia": 0.9,
        "t_amb_c": 25.0,
    }
    base.update(overrides)
    return base


def _seed_catalog(db):
    db.add_all([
        Gama(name="ATENEA"), Difusor(name="PMMA LC"), Lente(name="F151"), LedType(name="LUXEON HOP 5050"),
        Gama(name="OTRA"), Difusor(name="OTRO"), Lente(name="OTRA"),
    ])
    db.commit()


class _FakeResult:
    def __init__(self, config: CalculationConfig):
        self.config = config

    def model_dump(self) -> dict:
        return {
            "config": self.config.model_dump(),
            "compliant": True,
            "mode": "ME",
            "criteria": [],
            "Lavg": 1.2,
        }


def test_bulk_calculate_persists_optimized_config(monkeypatch):
    engine = create_test_engine()
    Base.metadata.create_all(engine)
    SessionTesting = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionTesting()
    try:
        _seed_catalog(db)
        project = Project(project_name="Test project", status="draft")
        db.add(project)
        db.flush()

        tramo = Tramo(
            project_id=project.id,
            name="Tramo 1",
            config_json=json.dumps(_base_config()),
        )
        db.add(tramo)
        db.commit()
        db.refresh(tramo)

        optimized = CalculationConfig(**_base_config(target_flux=11850.0, power=91.5))

        monkeypatch.setattr(
            tramo_operations,
            "run_flux_optimization",
            lambda _db, _config, **kw: SimpleNamespace(config=optimized),
        )
        monkeypatch.setattr(
            tramo_operations,
            "calculate_config",
            lambda _db, config, **kw: _FakeResult(config),
        )

        updated, failed = tramo_operations.bulk_calculate_tramos(db, [tramo], lambda item: item.id)

        assert updated == [tramo.id]
        assert failed == []

        db.refresh(tramo)
        saved_config = json.loads(tramo.config_json)
        saved_result = json.loads(tramo.result_json)

        assert saved_config["target_flux"] == 11850.0
        assert saved_config["power"] == 91.5
        assert saved_result["config"]["target_flux"] == 11850.0
        assert saved_result["config"]["power"] == 91.5
        assert saved_result["__configHash"] == tramo_operations.calculation_config_hash(saved_config)
        assert tramo.last_calculated_at is not None
    finally:
        db.close()
        engine.dispose()


def test_compliance_summary_uses_failed_criteria_over_raw_compliant():
    summary = _compliance_summary(json.dumps({
        "compliant": True,
        "Lavg": 1.2,
        "criteria": [
            {"name": "Lavg (cd/m²)", "passed": True},
            {"name": "Uo", "passed": False},
        ],
    }))

    assert summary["compliant"] is False
    assert summary["criteria_passed"]["Uo"] is False


def test_tramo_status_marks_no_pcb_capacity():
    tramo = SimpleNamespace(
        config_json=json.dumps(_base_config()),
        result_json=json.dumps({"__status": "no_pcb_capacity", "compliant": True, "Lavg": 1.2}),
    )

    assert _tramo_status(tramo) == "no_pcb_capacity"


def test_bulk_calculate_persists_no_pcb_capacity_status(monkeypatch):
    engine = create_test_engine()
    Base.metadata.create_all(engine)
    SessionTesting = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionTesting()
    try:
        _seed_catalog(db)
        project = Project(project_name="Test project", status="draft")
        db.add(project)
        db.flush()
        tramo = Tramo(project_id=project.id, name="Tramo 1", config_json=json.dumps(_base_config()))
        db.add(tramo)
        db.commit()
        db.refresh(tramo)

        monkeypatch.setattr(
            tramo_operations,
            "run_flux_optimization",
            lambda _db, _config, **kw: SimpleNamespace(config=_config, feasible=False, message="no_pcb"),
        )
        monkeypatch.setattr(
            tramo_operations,
            "calculate_config",
            lambda _db, config, **kw: _FakeResult(config),
        )

        updated, failed = tramo_operations.bulk_calculate_tramos(db, [tramo], lambda item: item.id)

        assert updated == [tramo.id]
        assert failed == []
        db.refresh(tramo)
        assert json.loads(tramo.result_json)["__status"] == "no_pcb_capacity"
        assert _tramo_status(tramo) == "no_pcb_capacity"
    finally:
        db.close()
        engine.dispose()


def test_no_pcb_capacity_detection_accepts_translated_message():
    optimization = SimpleNamespace(feasible=False, message="No hay una PCB que pueda entregar el flujo objetivo")

    assert tramo_operations._is_no_pcb_capacity(optimization) is True


def test_no_pcb_capacity_detection_ignores_lavg_compliant_result():
    optimization = SimpleNamespace(
        feasible=False,
        message="No PCB can deliver the target flux",
        result=SimpleNamespace(
            compliant=False,
            criteria=[
                SimpleNamespace(name="Lavg", passed=True),
                SimpleNamespace(name="SR", passed=False),
            ],
        ),
    )

    assert tramo_operations._is_no_pcb_capacity(optimization) is False


def test_no_pcb_error_detection_accepts_calculate_message():
    exc = ValueError("No PCB cumple los requisitos de flujo, I_op y lm/W mínimos.")

    assert tramo_operations._is_no_pcb_error(exc) is True


def test_bulk_calculate_marks_no_pcb_when_calculate_aborts(monkeypatch):
    engine = create_test_engine()
    Base.metadata.create_all(engine)
    SessionTesting = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionTesting()
    try:
        _seed_catalog(db)
        project = Project(project_name="Test project", status="draft")
        db.add(project)
        db.flush()
        tramo = Tramo(project_id=project.id, name="Tramo 1", config_json=json.dumps(_base_config()))
        db.add(tramo)
        db.commit()
        db.refresh(tramo)

        monkeypatch.setattr(
            tramo_operations,
            "run_flux_optimization",
            lambda _db, _config, **kw: SimpleNamespace(config=_config, feasible=True, message=""),
        )
        def fake_calculate(_db, config, **kw):
            if config.target_flux is not None:
                raise ValueError("No PCB cumple los requisitos de flujo, I_op y lm/W mínimos.")
            return _FakeResult(config)

        monkeypatch.setattr(tramo_operations, "calculate_config", fake_calculate)

        updated, failed = tramo_operations.bulk_calculate_tramos(db, [tramo], lambda item: item.id)

        assert updated == [tramo.id]
        assert failed == []
        db.refresh(tramo)
        saved_result = json.loads(tramo.result_json)
        assert saved_result["__status"] == "no_pcb_capacity"
        assert saved_result["criteria"] == []
        assert saved_result["config"]["target_flux"] is None
        assert _tramo_status(tramo) == "no_pcb_capacity"
    finally:
        db.close()
        engine.dispose()


def test_tramo_status_marks_missing_pcb_mapping_before_result():
    engine = create_test_engine()
    Base.metadata.create_all(engine)
    SessionTesting = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionTesting()
    try:
        _seed_catalog(db)
        tramo = SimpleNamespace(config_json=json.dumps(_base_config()), result_json=None)

        assert _tramo_status(tramo, db) == "no_pcb_capacity"
    finally:
        db.close()
        engine.dispose()


def test_tramo_status_context_marks_missing_pcb_mapping_before_result():
    engine = create_test_engine()
    Base.metadata.create_all(engine)
    SessionTesting = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionTesting()
    try:
        _seed_catalog(db)
        tramo = SimpleNamespace(config_json=json.dumps(_base_config()), result_json=None)

        assert _tramo_status(tramo, status_context=_build_status_context(db)) == "no_pcb_capacity"
    finally:
        db.close()
        engine.dispose()
