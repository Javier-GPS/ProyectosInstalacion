"""Tests for PCB upload / create endpoint.

Uses an isolated PostgreSQL schema created from the project's models.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import sessionmaker

from conftest import create_test_engine

from app.database import Base
from app.models import PCB
from app.services import catalog_service


@pytest.fixture()
def db():
    engine = create_test_engine()
    Base.metadata.create_all(engine)
    SessionTesting = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionTesting()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_create_pcb_returns_all_fields(db):
    data = {
        "pcb_ref": "1ME2432",
        "pcb_descripcion": "PCB 18 LED 5050",
        "pcb_no_drivers": 1,
        "pcb_v_nominal": 5.9,
        "pcb_no_led": 18,
        "pcb_no_circuitos": 3,
        "pcb_imax_led": 1.2,
    }
    result = catalog_service.create_pcb(db, data)
    assert result["pcb_ref"] == "1ME2432"
    assert result["pcb_descripcion"] == "PCB 18 LED 5050"
    assert result["pcb_no_drivers"] == 1
    assert result["pcb_v_nominal"] == 5.9
    assert result["pcb_no_led"] == 18
    assert result["pcb_no_circuitos"] == 3
    assert result["pcb_imax_led"] == 1.2
    assert isinstance(result["id"], int)


def test_create_pcb_minimal_fields(db):
    data = {"pcb_ref": "MINI001"}
    result = catalog_service.create_pcb(db, data)
    assert result["pcb_ref"] == "MINI001"
    assert result["pcb_descripcion"] is None
    assert result["pcb_no_drivers"] is None


def test_create_pcb_upserts_on_same_ref(db):
    data = {"pcb_ref": "1ME2432", "pcb_descripcion": "v1", "pcb_v_nominal": 5.9}
    r1 = catalog_service.create_pcb(db, data)
    assert r1["pcb_descripcion"] == "v1"

    data2 = {"pcb_ref": "1ME2432", "pcb_descripcion": "v2", "pcb_v_nominal": 6.0}
    r2 = catalog_service.create_pcb(db, data2)
    assert r2["id"] == r1["id"]
    assert r2["pcb_descripcion"] == "v2"
    assert r2["pcb_v_nominal"] == 6.0


def test_create_pcb_preserves_unchanged_fields_on_upsert(db):
    data = {"pcb_ref": "1ME2432", "pcb_descripcion": "v1", "pcb_no_led": 18}
    catalog_service.create_pcb(db, data)
    data2 = {"pcb_ref": "1ME2432", "pcb_descripcion": "v2"}
    r2 = catalog_service.create_pcb(db, data2)
    assert r2["pcb_descripcion"] == "v2"
    assert r2["pcb_no_led"] == 18


def test_list_pcbs_includes_all_fields(db):
    catalog_service.create_pcb(db, {"pcb_ref": "A1", "pcb_descripcion": "descA", "pcb_v_nominal": 12.0})
    catalog_service.create_pcb(db, {"pcb_ref": "B2", "pcb_descripcion": "descB", "pcb_no_led": 24})
    rows = catalog_service.list_pcbs(db)
    assert len(rows) == 2
    assert rows[0]["pcb_descripcion"] == "descA"
    assert rows[1]["pcb_descripcion"] == "descB"
    assert rows[0]["pcb_v_nominal"] == 12.0
    assert rows[1]["pcb_no_led"] == 24
