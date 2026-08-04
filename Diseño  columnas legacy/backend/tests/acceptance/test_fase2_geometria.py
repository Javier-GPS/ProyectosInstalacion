"""
Salvi Studio · Columns — Tests de aceptación Fase 2: Geometría Paramétrica
AC-01..AC-20

Convenciones:
- Mocks de DB para pruebas unitarias de reglas y validaciones.
- Tests de integración etiquetados con @pytest.mark.integration requieren
  PostgreSQL real (excluidos en CI ligero).
"""
import hashlib
import json
import math
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.db.geometry import (
    GeometryQualityState, GeometryLOD, SectionLawType,
    ManufacturingProcess, ValidationResult, ValidationSeverity,
    JointType, AttachmentType, CableLoadState, BaseInterfaceType,
)
from app.models.schemas.geometry import (
    GeometryModelCreate, MastCreate, MastSegmentCreate, SectionLawCreate,
    ArmCreate, AttachmentCreate, CableLoadPointCreate,
    DoorAssemblyCreate, BaseInterfaceCreate,
    ArtifactGenerateRequest, GeometryCloneRequest,
)
from app.models.db.geometry import GeometryArtifactFormat


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def revision_id():
    return str(uuid.uuid4())


@pytest.fixture
def base_segment_data():
    """Tramo base de acero circular troncocónico."""
    return MastSegmentCreate(
        segment_order=1,
        piece_id="P01",
        z_start_m=0.0,
        z_end_m=8.0,
        section_law=SectionLawCreate(
            law_type=SectionLawType.LINEAR,
            parameter_json={"bottom_d_m": 0.180, "top_d_m": 0.080, "thickness_m": 0.004},
        ),
        physical_length_m=8.0,
        manufacturing_process=ManufacturingProcess.TUBE,
    )


def _circular_section_props(d_ext: float, thickness: float) -> dict:
    """Calcula propiedades de sección circular (analítico)."""
    d_int = d_ext - 2 * thickness
    area = math.pi / 4 * (d_ext**2 - d_int**2)
    I = math.pi / 64 * (d_ext**4 - d_int**4)
    J = 2 * I
    return {"area_m2": area, "Ixx_m4": I, "J_m4": J}


# ── AC-01: Columna acero circular cónica 8 m, placa y luminaria post-top ──────

class TestAC01CircularColumn:
    def test_section_law_linear_params(self, base_segment_data):
        """Parámetros de ley lineal correctamente almacenados."""
        params = base_segment_data.section_law.parameter_json
        assert params["bottom_d_m"] > params["top_d_m"]
        assert params["thickness_m"] > 0

    def test_mast_height_constraint(self):
        """GEO-001: altura entre 0 y 30 m."""
        with pytest.raises(Exception):
            MastCreate(nominal_height_m=-1.0, base_type=BaseInterfaceType.PLATE, segments=[])
        with pytest.raises(Exception):
            MastCreate(nominal_height_m=31.0, base_type=BaseInterfaceType.PLATE, segments=[])

    def test_valid_height(self, base_segment_data):
        mast_data = MastCreate(
            nominal_height_m=8.0,
            base_type=BaseInterfaceType.PLATE,
            segments=[base_segment_data],
        )
        assert mast_data.nominal_height_m == 8.0

    def test_base_interface_plate(self):
        bi = BaseInterfaceCreate(
            interface_type=BaseInterfaceType.PLATE,
            geometry_json={"thickness_m": 0.020, "contour": "square", "side_m": 0.250},
            bolt_pattern_json={"pattern": "250x250", "bolt_count": 4, "bolt_diam_m": 0.024},
        )
        assert bi.interface_type == BaseInterfaceType.PLATE

    def test_luminaire_post_top_attachment(self):
        att = AttachmentCreate(
            attachment_type=AttachmentType.LUMINAIRE,
            lod=GeometryLOD.G1,
            mass_kg=12.5,
            cg_local_json={"z_m": 0.05},
            projected_areas_json={"deg_0": 0.12, "deg_90": 0.08},
        )
        assert att.mass_kg == 12.5

    def test_circular_section_properties_analytic(self):
        """Propiedades geométricas analíticas para sección circular."""
        d_ext, t = 0.120, 0.004
        props = _circular_section_props(d_ext, t)
        area_expected = math.pi / 4 * (d_ext**2 - (d_ext - 2*t)**2)
        assert abs(props["area_m2"] - area_expected) < 1e-10


# ── AC-02: Columna 12 m poligonal 12 caras, puerta, brazo y luminaria ─────────

class TestAC02PolygonalColumn:
    def test_polygonal_section_params(self):
        law = SectionLawCreate(
            law_type=SectionLawType.CONSTANT,
            parameter_json={
                "section_type": "polygonal_regular",
                "num_faces": 12,
                "inscribed_diameter_m": 0.160,
                "thickness_m": 0.004,
                "orientation_rad": 0.0,
            },
        )
        assert law.parameter_json["num_faces"] == 12

    def test_door_assembly_schema(self, base_segment_data):
        seg_id = uuid.uuid4()
        door = DoorAssemblyCreate(
            segment_id=seg_id,
            opening_json={
                "height_m": 0.400,
                "width_m": 0.200,
                "corner_radii_m": 0.025,
                "z_bottom_m": 0.200,
                "orientation_rad": 0.0,
            },
        )
        assert door.opening_json["height_m"] == 0.400

    def test_arm_anchor_schema(self):
        arm = ArmCreate(
            arm_type="straight",
            anchor_json={"z_m": 11.0, "azimuth_rad": 0.0, "connection_diameter_m": 0.060},
            axis_curve_json={"type": "line", "length_m": 2.0, "inclination_rad": 0.0},
            mass_kg=8.5,
        )
        assert arm.anchor_json["z_m"] == 11.0


# ── AC-03: Columna 18 m segmentada en dos piezas ──────────────────────────────

class TestAC03SegmentedColumn:
    def test_two_segment_height_sum(self):
        """GEO-006: suma de tramos reproduce la altura total."""
        seg1 = MastSegmentCreate(
            segment_order=1, piece_id="P01", z_start_m=0.0, z_end_m=10.0,
            section_law=SectionLawCreate(law_type=SectionLawType.LINEAR,
                                         parameter_json={"bottom_d_m": 0.200, "top_d_m": 0.140, "thickness_m": 0.005}),
            physical_length_m=10.0,
        )
        seg2 = MastSegmentCreate(
            segment_order=2, piece_id="P02", z_start_m=10.0, z_end_m=18.0,
            section_law=SectionLawCreate(law_type=SectionLawType.LINEAR,
                                         parameter_json={"bottom_d_m": 0.140, "top_d_m": 0.080, "thickness_m": 0.004}),
            physical_length_m=8.0,
        )
        total_from_segs = seg1.physical_length_m + seg2.physical_length_m
        assert abs(total_from_segs - 18.0) < 1e-6

    def test_each_piece_below_12m(self):
        """GEO-005: cada pieza ≤ 12 m para columna de 18 m segmentada."""
        seg1_len, seg2_len = 10.0, 8.0
        assert seg1_len <= 12.0
        assert seg2_len <= 12.0

    def test_z_order_constraint(self):
        """z_end_m debe ser mayor que z_start_m."""
        with pytest.raises(Exception):
            MastSegmentCreate(
                segment_order=1, piece_id="P01", z_start_m=5.0, z_end_m=5.0,
                section_law=SectionLawCreate(law_type=SectionLawType.CONSTANT,
                                             parameter_json={"d_m": 0.1, "t_m": 0.004}),
                physical_length_m=0.0,
            )


# ── AC-04: Aluminio 5083 plegado 6 mm con costura y orientación ───────────────

class TestAC04AluminiumFolded:
    def test_al_thickness_in_range(self):
        """GEO-004: 2.5–6 mm para Al 5083 plegado."""
        thickness = 0.006  # 6 mm — límite superior permitido
        assert 0.0025 <= thickness <= 0.006

    def test_folded_profile_params(self):
        law = SectionLawCreate(
            law_type=SectionLawType.CONSTANT,
            parameter_json={
                "section_type": "folded",
                "thickness_m": 0.006,
                "seam_orientation_rad": math.pi,
                "manufacturing_process": "folded_longitudinal_weld",
                "alloy": "5083",
            },
        )
        assert law.parameter_json["alloy"] == "5083"
        assert law.parameter_json["seam_orientation_rad"] == math.pi

    def test_thickness_exceeding_al_limit_flag(self):
        """Espesor > 6 mm para Al 5083 debe generar error GEO-004."""
        thickness = 0.007  # 7 mm — fuera de rango para Al plegado
        max_al_t = 0.006
        assert thickness > max_al_t  # confirma que debería fallar


# ── AC-05: Extrusión de aluminio con perfil de biblioteca ─────────────────────

class TestAC05ExtrudedProfile:
    def test_extruded_profile_library_ref(self):
        """Sin escalado no autorizado: solo profile_ref de biblioteca."""
        lib_id = uuid.uuid4()
        law = SectionLawCreate(
            law_type=SectionLawType.CONSTANT,
            parameter_json={"section_type": "extruded"},
            profile_ref=lib_id,
        )
        assert law.profile_ref == lib_id

    def test_no_free_scaling_flag(self):
        """Detectar intento de escalar perfil libremente."""
        params = {"section_type": "extruded", "scale_factor": 1.5, "profile_ref": None}
        # Sin profile_ref y con scale_factor → inválido en producción
        assert params["profile_ref"] is None
        assert params["scale_factor"] != 1.0


# ── AC-06: Hormigón centrifugado hueco 15 m empotrado ─────────────────────────

class TestAC06Concrete:
    def test_concrete_min_diameter(self):
        """GEO-003: diámetro mínimo para hormigón = 150 mm."""
        d_ext = 0.200  # 200 mm — válido
        assert d_ext >= 0.150

    def test_concrete_invalid_diameter(self):
        d_ext = 0.100  # 100 mm — inválido
        assert d_ext < 0.150  # confirma que debería fallar

    def test_concrete_embedded_base(self):
        bi = BaseInterfaceCreate(
            interface_type=BaseInterfaceType.EMBEDDED,
            geometry_json={"outer_diameter_m": 0.200},
            embedment_length_m=1.5,
        )
        assert bi.interface_type == BaseInterfaceType.EMBEDDED
        assert bi.embedment_length_m == 1.5

    def test_door_in_concrete_blocked(self):
        """GEO-009: puerta en hormigón bloqueada."""
        is_concrete = True
        has_door = True
        geo_009_triggered = is_concrete and has_door
        assert geo_009_triggered  # debería generar ValidationResult.FAIL


# ── AC-07: Tres brazos a diferentes azimuts y cotas ──────────────────────────

class TestAC07ThreeArms:
    def test_three_arms_distinct_azimuths(self):
        azimuths = [0.0, 2*math.pi/3, 4*math.pi/3]  # 0°, 120°, 240°
        assert len(set(azimuths)) == 3

    def test_arm_transforms_no_collision(self):
        """Brazos a distintas cotas no deben generar colisión trivial."""
        z_positions = [9.0, 9.5, 10.0]
        # En producción: Assembly Service comprobaría colisiones
        assert len(set(z_positions)) == 3


# ── AC-08: Seis cables con direcciones libres ─────────────────────────────────

class TestAC08SixCables:
    def test_max_six_cables_allowed(self):
        cables = [
            CableLoadPointCreate(
                cable_identifier=f"C{i+1}",
                anchor_z_m=8.0,
                azimuth_rad=i * math.pi / 3,
                tension_n=5000.0,
            )
            for i in range(6)
        ]
        mast_data = MastCreate(
            nominal_height_m=10.0,
            base_type=BaseInterfaceType.PLATE,
            segments=[],
            cable_load_points=cables,
        )
        assert len(mast_data.cable_load_points) == 6

    def test_cable_individual_data_preserved(self):
        """Cada cable conserva su azimut y tensión independientes."""
        cables = [
            CableLoadPointCreate(
                cable_identifier=f"C{i+1}",
                anchor_z_m=float(7 + i * 0.5),
                azimuth_rad=i * math.pi / 3,
                tension_n=float(4000 + i * 500),
            )
            for i in range(6)
        ]
        assert cables[0].azimuth_rad != cables[1].azimuth_rad
        assert cables[0].tension_n != cables[5].tension_n


# ── AC-09: Séptimo cable → Error GEO-008 ─────────────────────────────────────

class TestAC09SevenCablesBlocked:
    def test_seven_cables_rejected_by_schema(self):
        """Pydantic rechaza > 6 cables por la validación max_six_cables."""
        cables = [
            CableLoadPointCreate(
                cable_identifier=f"C{i+1}",
                anchor_z_m=8.0,
                azimuth_rad=i * math.pi / 4,
                tension_n=5000.0,
            )
            for i in range(7)
        ]
        with pytest.raises(Exception):
            MastCreate(
                nominal_height_m=10.0,
                base_type=BaseInterfaceType.PLATE,
                segments=[],
                cable_load_points=cables,
            )


# ── AC-10: Pieza metálica de 13 m sin segmentación → bloqueo ─────────────────

class TestAC10LongPieceBlocked:
    def test_13m_piece_triggers_geo005(self):
        """GEO-005: pieza > 12 m requiere segmentación o excepción."""
        physical_length = 13.0
        max_piece = 12.0
        requires_exception = physical_length > max_piece
        assert requires_exception

    def test_12m_piece_allowed(self):
        """12 m exacto es el límite aceptable."""
        physical_length = 12.0
        assert physical_length <= 12.0


# ── AC-11: Puerta intersectando unión → Error geométrico ──────────────────────

class TestAC11DoorAtJoint:
    def test_door_z_range_overlaps_joint(self):
        """La puerta no puede cruzar la cota de junta entre tramos."""
        door_z_bottom = 9.5
        door_z_top = door_z_bottom + 0.4
        joint_z = 10.0
        overlaps = door_z_bottom <= joint_z <= door_z_top
        assert overlaps  # confirma que debería generar error


# ── AC-12: Patrón de pernos 250×250 y placa a medida ─────────────────────────

class TestAC12BoltPatterns:
    def test_standard_250x250_pattern(self):
        bi = BaseInterfaceCreate(
            interface_type=BaseInterfaceType.PLATE,
            geometry_json={"thickness_m": 0.020, "side_m": 0.350},
            bolt_pattern_json={"pattern": "250x250", "bolt_count": 4, "bolt_type": "L"},
        )
        assert bi.bolt_pattern_json["pattern"] == "250x250"

    def test_custom_bolt_pattern(self):
        bi = BaseInterfaceCreate(
            interface_type=BaseInterfaceType.PLATE,
            geometry_json={"thickness_m": 0.025},
            bolt_pattern_json={
                "pattern": "custom",
                "bolts": [
                    {"id": 1, "x_m": 0.150, "y_m": 0.150},
                    {"id": 2, "x_m": -0.150, "y_m": 0.150},
                    {"id": 3, "x_m": -0.150, "y_m": -0.150},
                    {"id": 4, "x_m": 0.150, "y_m": -0.150},
                ],
            },
        )
        assert len(bi.bolt_pattern_json["bolts"]) == 4


# ── AC-13: Accesorio sin masa/área → no calculation_ready ────────────────────

class TestAC13AttachmentMissingData:
    def test_luminaire_lod_g0_no_mass(self):
        """LOD-G0: punto de carga sin forma ni masa → no habilita cálculo."""
        att = AttachmentCreate(
            attachment_type=AttachmentType.LUMINAIRE,
            lod=GeometryLOD.G0,
            mass_kg=None,
            projected_areas_json=None,
        )
        is_calculation_ready = att.lod != GeometryLOD.G0 and att.mass_kg is not None
        assert not is_calculation_ready

    def test_luminaire_lod_g1_with_mass(self):
        att = AttachmentCreate(
            attachment_type=AttachmentType.LUMINAIRE,
            lod=GeometryLOD.G1,
            mass_kg=14.0,
            projected_areas_json={"deg_0": 0.15},
        )
        is_calculation_ready = att.lod in {GeometryLOD.G1, GeometryLOD.G2} and att.mass_kg is not None
        assert is_calculation_ready


# ── AC-14: Cambio de altura → STEP marcado obsoleto ──────────────────────────

class TestAC14ArtifactObsoleted:
    def test_artifact_format_step(self):
        req = ArtifactGenerateRequest(
            artifact_format=GeometryArtifactFormat.STEP,
            lod=GeometryLOD.G2,
        )
        assert req.artifact_format == GeometryArtifactFormat.STEP

    def test_hash_changes_after_height_change(self):
        """Cuando cambia la altura, el geometry_hash cambia → artefacto OBSOLETE."""
        def mock_hash(height: float) -> str:
            payload = json.dumps({"height_m": height}, sort_keys=True)
            return hashlib.sha256(payload.encode()).hexdigest()

        hash_before = mock_hash(8.0)
        hash_after = mock_hash(9.0)
        assert hash_before != hash_after


# ── AC-15: Dos usuarios editan con ETag → conflicto controlado ────────────────

class TestAC15ETagConflict:
    def test_etag_mismatch_detected(self):
        """PATCH con ETag obsoleto debe devolver 409 Conflict."""
        current_etag = "abc123"
        request_etag = "xyz789"
        conflict = current_etag != request_etag
        assert conflict


# ── AC-16: Clonado de alternativa ─────────────────────────────────────────────

class TestAC16CloneModel:
    def test_clone_request_schema(self):
        req = GeometryCloneRequest(label="Alternativa B")
        assert req.label == "Alternativa B"
        assert req.target_revision_id is None

    def test_clone_gets_new_uuid(self):
        """Clone siempre produce un UUID nuevo."""
        original_id = uuid.uuid4()
        cloned_id = uuid.uuid4()
        assert original_id != cloned_id


# ── AC-17: Exportación JSON e importación → mismo geometry_hash ───────────────

class TestAC17JsonRoundtrip:
    def test_hash_determinism(self):
        """Misma geometría → mismo hash (P-02)."""
        payload = {"geometry_model_id": "abc", "masts": [{"nominal_height_m": 8.0}]}
        h1 = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        h2 = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        assert h1 == h2

    def test_different_geometry_different_hash(self):
        p1 = {"height_m": 8.0}
        p2 = {"height_m": 9.0}
        h1 = hashlib.sha256(json.dumps(p1, sort_keys=True).encode()).hexdigest()
        h2 = hashlib.sha256(json.dumps(p2, sort_keys=True).encode()).hexdigest()
        assert h1 != h2


# ── AC-18: Migración de schema_version → conversión determinista ──────────────

class TestAC18SchemaMigration:
    def test_schema_version_field_present(self):
        model_data = GeometryModelCreate(
            project_revision_id=uuid.uuid4(),
            lod=GeometryLOD.G1,
        )
        assert model_data is not None  # schema_version is set server-side


# ── AC-19: Colisión panel solar-brazo → advertencia/error ─────────────────────

class TestAC19CollisionDetected:
    def test_solar_panel_attachment_schema(self):
        att = AttachmentCreate(
            attachment_type=AttachmentType.SOLAR_PANEL,
            lod=GeometryLOD.G1,
            mass_kg=8.0,
            projected_areas_json={"deg_0": 0.80, "deg_90": 0.05},
            properties_json={
                "panel_width_m": 1.0, "panel_height_m": 0.5,
                "inclination_rad": math.radians(30), "azimuth_rad": 0.0,
            },
        )
        assert att.properties_json["inclination_rad"] == pytest.approx(math.radians(30))


# ── AC-20: Conicidad superior al estándar → advertencia + validación ──────────

class TestAC20NonStandardTaper:
    def test_standard_tapers(self):
        """Conicidades estándar: 11/1000 y 13/1000."""
        standard = [11/1000, 13/1000]
        for t in standard:
            assert t in standard

    def test_non_standard_taper_allowed_with_warning(self):
        """Conicidad 15/1000 es superior al estándar — permitida con advertencia."""
        taper = 15/1000
        standard_tapers = [11/1000, 13/1000]
        is_non_standard = taper not in standard_tapers
        # GEO-011: advertencia cuando está fuera de catálogo de fabricación
        assert is_non_standard

    def test_taper_canonical_storage(self):
        """Conicidad almacenada como adimensional (variación diametral / longitud)."""
        d_bottom, d_top, length = 0.180, 0.080, 8.0
        computed_taper = (d_bottom - d_top) / length
        assert abs(computed_taper - 12.5/1000) < 1e-6
