from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_serializer
from typing import Optional


class RoadElement(BaseModel):
    """A single element in a road cross-section (left to right).

    Types:

    - ``carriageway`` — vehicular lane strip; ``lanes`` and ``lighting_class``
      apply to this strip only.
    - ``sidewalk`` — pedestrian strip; ``pedestrian_class`` applies.

    All elements in a ``road_elements`` list are concatenated left to right
    to form the full road cross-section.  When ``road_elements`` is non-empty
    the legacy flat fields (``road_width``, ``sidewalk_left``, …) are ignored
    and recomputed from the list on save.
    """

    type: str = Field(pattern=r"^(carriageway|sidewalk)$")
    width: float = Field(ge=0, le=30, description="Width of this element in meters")
    lanes: Optional[int] = Field(default=None, ge=1, le=6, description="Number of lanes (carriageway only)")
    lighting_class: Optional[str] = Field(
        default=None, pattern=r"^(M[1-6])$",
        description="EN 13201 class for this carriageway (carriageway only)",
    )
    pedestrian_class: Optional[str] = Field(
        default=None, pattern=r"^(P[1-7])$",
        description="EN 13201 pedestrian class for this strip (sidewalk only)",
    )


def road_elements_from_flat(
    road_width: float = 7.0,
    sidewalk_left: float = 0.0,
    sidewalk_right: float = 0.0,
    sidewalk_left_class: str = "P4",
    sidewalk_right_class: str = "P4",
    lanes: int = 2,
    lighting_class: str = "M3",
    median_width: float = 0.0,
    median_class: str = "P4",
) -> list[RoadElement]:
    """Build a ``road_elements`` list from the old flat fields.

    Used when loading a tramo saved before the road-elements migration so
    the FE always works with the element-based model internally.
    """
    elements: list[RoadElement] = []
    if sidewalk_left > 0:
        elements.append(RoadElement(type="sidewalk", width=sidewalk_left, pedestrian_class=sidewalk_left_class))
    elements.append(RoadElement(type="carriageway", width=road_width, lanes=lanes, lighting_class=lighting_class))
    if median_width > 0:
        elements.append(RoadElement(type="sidewalk", width=median_width, pedestrian_class=median_class))
    if sidewalk_right > 0:
        elements.append(RoadElement(type="sidewalk", width=sidewalk_right, pedestrian_class=sidewalk_right_class))
    return elements


class CalculationConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    road_width: float = Field(ge=0.5, le=30, default=7.0, description="Road width in meters")
    sidewalk_left: float = Field(ge=0, le=10, default=0)
    sidewalk_right: float = Field(ge=0, le=10, default=0)
    lanes: int = Field(ge=1, le=6, default=2)
    road_elements: list[RoadElement] = Field(
        default_factory=list,
        description="Ordered list of road cross-section elements (left to right). "
        "When non-empty the legacy flat geometry fields are derived from this list.",
    )
    arrangement: str = Field(
        default="Lineal",
        pattern=r"^(Lineal|Bilateral|Bilateral Alternada|Central Doble|En Isleta)$",
    )
    height: float = Field(ge=4, le=40, default=9, description="Pole height in meters")
    spacing: float = Field(ge=5, le=60, default=30, description="Pole spacing in meters")
    arm_length: float = Field(
        ge=0,
        le=5,
        default=1.5,
        validation_alias=AliasChoices("arm_length", "armLength"),
        description="Bracket length in meters",
    )
    pole_offset: float = Field(ge=0, le=5, default=0, description="Distance from road edge to pole axis in meters")
    pole_side: str = Field(default="left", pattern=r"^(left|right)$", description="Road side where unilateral poles are installed")
    tilt: float = Field(
        ge=-30,
        le=30,
        default=5,
        validation_alias=AliasChoices("tilt", "armTiltAngle"),
        description="Tilt Angle in degrees",
    )
    optic_family: str = Field(description="Optic family code, e.g. F151")
    power: float = Field(ge=0, description="Luminaire power in watts. 0 means auto-compute from target_flux.")
    ldt_id: Optional[str] = None
    manufacturer: Optional[str] = None
    model_family: Optional[str] = None
    # 4-tuple catalog selection.  Optional so legacy LDTs (no
    # catalog row) keep working; the cap is only enforced when all
    # four are present and resolve to a known LED.
    gama: Optional[str] = None
    difusor: Optional[str] = None
    lente: Optional[str] = None
    led_type: Optional[str] = None
    lighting_class: str = Field(
        default="M3",
        pattern=r"^(M[1-6]|P[1-6])$",
        description="EN 13201 lighting class",
    )
    sidewalk_left_class: Optional[str] = Field(
        default=None, pattern=r"^(P[1-7])$",
        description="EN 13201 pedestrian class for left sidewalk",
    )
    sidewalk_right_class: Optional[str] = Field(
        default=None, pattern=r"^(P[1-7])$",
        description="EN 13201 pedestrian class for right sidewalk",
    )
    median_class: Optional[str] = Field(
        default=None, pattern=r"^(P[1-7])$",
        description="EN 13201 pedestrian class for median",
    )
    mf: float = Field(ge=0.5, le=1.0, default=0.85, description="Maintenance factor")
    pavement: str = Field(default="R3", pattern=r"^R[1-4]$")
    cct: int = Field(default=4000, ge=1800, le=6500)
    cri: int = Field(default=70, ge=70, le=90)
    t_amb_c: Optional[float] = Field(default=25.0, ge=-40, le=80, description="Ambient temperature in °C; used by the LUXEON 5050 V2 model to compute Tsp = T_amb + coef × P_luminaire.")
    margen_lavg: Optional[float] = Field(default=0.0, ge=0, le=100, description="Margen porcentual a añadir al Lavg objetivo para la optimización")
    target_flux: Optional[float] = Field(default=None, ge=0, description="Target luminous flux in lm. When set, power is computed from PCB selection rather than used directly.")
    i_op_ma: Optional[float] = Field(default=None, ge=0, description="Operating current per LED in mA")
    lm_w_min: Optional[float] = Field(default=None, ge=0, description="Minimum acceptable efficacy in lm/W")
    driver_eficiencia: Optional[float] = Field(default=None, ge=0, le=1, description="Driver efficiency factor (0-1)")
    language: str = Field(default="es", pattern=r"^(es|en|fr|pt|de|it)$")
    selected_pcb_ref: Optional[str] = Field(default=None, description="PCB reference to force (flux-driven mode)")
    median_width: float = Field(ge=0, le=20, default=0, description="Median strip width. Splits the carriageway into two sub-carriageways for Central Doble arrangements.")
    illuminance_scale_mode: str = Field(default="auto", pattern=r"^(auto|manual)$", description="3D scene scale mode (visual-only)")
    illuminance_scale_min: float = Field(default=0, ge=0, description="3D scene scale min (visual-only)")
    illuminance_scale_max: float = Field(default=50, ge=0, le=200, description="3D scene scale max (visual-only)")
    photometric_display_unit: str = Field(default="lux", pattern=r"^(lux|candela)$", description="3D scene display unit (visual-only)")
    generate_buildings: bool = Field(default=False, description="Toggle 3D buildings (visual-only)")
    building_height: float = Field(default=12, ge=0, le=100, description="Building height (visual-only)")
    buildings_as_obstacles: bool = Field(default=False, description="Treat buildings as obstacles (visual-only)")


class FotometriaInfo(BaseModel):
    id: str
    filename: str
    luminaire_name: str
    manufacturer: str = "Unknown"
    model_family: str = "UNKNOWN"
    cct: int = 4000
    cri: int = 70
    optic_family: str
    power: float
    flux: float
    efficiency: float
    LORL: float
    isym: int
    gama: Optional[str] = None
    difusor: Optional[str] = None
    lente: Optional[str] = None
    led_type: Optional[str] = None
    fotometria: Optional[str] = None
    mf_origen: float = Field(
        ge=0.5, le=1.0, default=1.0,
        description="Maintenance factor already baked into the LDT candela values "
                    "(1.0 = raw LDT, the user-supplied config.mf is applied verbatim)",
    )


# Legacy alias — keep LDTInfo as a backward-compatible re-export.
LDTInfo = FotometriaInfo


class LuminairePcbInfo(BaseModel):
    gama: Optional[str] = None
    difusor: Optional[str] = None
    lente: Optional[str] = None
    led_type: Optional[str] = None
    pcb_ref: Optional[str] = None
    pcb_descripcion: Optional[str] = None
    pcb_v_nominal: Optional[float] = None
    pcb_imax_led: Optional[float] = None
    pcb_no_led: Optional[int] = None
    n_pcbs: Optional[int] = None
    n_leds_per_pcb: Optional[int] = None
    total_n_leds: Optional[int] = None
    led_ref: Optional[str] = None


class FluxDetail(LuminairePcbInfo):
    flux: float = 0
    efficiency: float = 0
    led_efficacy: float = 0
    lente_eficiencia: Optional[float] = None
    difusor_eficiencia: Optional[float] = None
    thermal_derating: float = 1.0
    v_f: float = 0
    p_led: float = 0
    p_total: float = 0
    i_op_ma: float = 500
    user_i_op_ma: Optional[float] = None
    user_lm_w_min: Optional[float] = None
    i_op_ok: bool = True
    lm_w_ok: bool = True
    driver_eficiencia: float = 1.0
    available_pcbs: list["PcbOption"] = Field(default_factory=list)


class PcbOption(BaseModel):
    pcb_ref: Optional[str] = None
    pcb_descripcion: Optional[str] = None
    pcb_imax_led: Optional[float] = None
    pcb_v_nominal: Optional[float] = None
    n_pcbs: Optional[int] = None
    n_leds_per_pcb: Optional[int] = None
    total_n_leds: Optional[int] = None
    led_ref: Optional[str] = None


class LDTFamily(BaseModel):
    code: str
    description: str
    ldts: list[FotometriaInfo]


class ElementResult(BaseModel):
    """Per-element calculation result for multi-carriageway roads."""
    index: int
    type: str  # "carriageway" | "sidewalk"
    width: float = 0
    lighting_class: Optional[str] = None
    compliant: bool = True
    Lavg: Optional[float] = None
    Uo: Optional[float] = None
    Ul: Optional[float] = None
    TI: Optional[float] = None
    SR: Optional[float] = None
    EIR: Optional[float] = None
    Eavg: Optional[float] = None
    Emin: Optional[float] = None
    Eavg_ped: Optional[float] = None
    Emin_ped: Optional[float] = None
    pedestrian_class: Optional[str] = None
    criteria_passed: dict[str, bool] = Field(default_factory=dict)
    criteria_required: dict[str, float] = Field(default_factory=dict)

    @field_serializer(
        "Lavg", "Uo", "Ul", "TI", "SR", "EIR",
        "Eavg", "Emin", "Eavg_ped", "Emin_ped",
        when_used="json",
    )
    def _serialize_metric(self, value: Optional[float]) -> Optional[float]:
        return round(value, 2) if value is not None else None


class CriterionResult(BaseModel):
    name: str
    value: float
    required: float
    passed: bool
    is_compliance_criterion: bool = True

    @field_serializer("value", when_used="json")
    def _serialize_value(self, value: float) -> float:
        return round(value, 2)


class CalculationResult(BaseModel):
    config: CalculationConfig
    compliant: bool
    mode: str
    luminaire: FotometriaInfo
    criteria: list[CriterionResult]
    elements: list[ElementResult] = Field(default_factory=list)
    Eavg: Optional[float] = None
    Emin: Optional[float] = None
    Lavg: Optional[float] = None
    Uo: Optional[float] = None
    Ul: Optional[float] = None
    TI: Optional[float] = None
    SR: Optional[float] = None
    EIR: Optional[float] = None
    sidewalk_left_Eavg: Optional[float] = None
    sidewalk_left_Emin: Optional[float] = None
    sidewalk_left_class: Optional[str] = None
    sidewalk_right_Eavg: Optional[float] = None
    sidewalk_right_Emin: Optional[float] = None
    sidewalk_right_class: Optional[str] = None

    @field_serializer(
        "Eavg", "Emin", "Lavg", "Uo", "Ul", "TI", "SR", "EIR",
        "sidewalk_left_Eavg", "sidewalk_left_Emin",
        "sidewalk_right_Eavg", "sidewalk_right_Emin",
        when_used="json",
    )
    def _serialize_metric(self, value: Optional[float]) -> Optional[float]:
        return round(value, 2) if value is not None else None


class MeasurementGrid(BaseModel):
    title: str
    unit: str
    xs: list[float]
    ys: list[float]
    values: list[list[float]]
    avg: float
    min: float
    max: float
    uniformity_avg: float
    uniformity_max: float


class MeasurementResponse(BaseModel):
    config: CalculationConfig
    luminaire: FotometriaInfo
    primary: str
    grids: dict[str, MeasurementGrid]


class BatchCalculationItem(BaseModel):
    model_id: str
    row: int
    config: Optional[CalculationConfig] = None
    result: Optional[CalculationResult] = None
    error: Optional[str] = None


class BatchCalculationResponse(BaseModel):
    filename: str
    count: int
    items: list[BatchCalculationItem]


class OptimizationResponse(BaseModel):
    feasible: bool
    message: str
    objective: str
    fixed_parameters: list[str]
    checked: int
    config: Optional[CalculationConfig] = None
    result: Optional[CalculationResult] = None


class AdvancedOptimizationVariables(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    power: bool = True
    spacing: bool = False
    height: bool = False
    arm_length: bool = Field(default=False, validation_alias=AliasChoices("arm_length", "armLength"))
    tilt: bool = Field(default=False, validation_alias=AliasChoices("tilt", "armTiltAngle"))
    optic_family: bool = False


class AdvancedOptimizationLimits(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    power: Optional[float] = None
    spacing: Optional[float] = None
    height: Optional[float] = None
    arm_length: Optional[float] = Field(default=None, validation_alias=AliasChoices("arm_length", "armLength"))
    tilt: Optional[float] = Field(default=None, validation_alias=AliasChoices("tilt", "armTiltAngle"))


class AdvancedOptimizationRequest(BaseModel):
    config: CalculationConfig
    variables: AdvancedOptimizationVariables = Field(default_factory=AdvancedOptimizationVariables)
    limits: AdvancedOptimizationLimits = Field(default_factory=AdvancedOptimizationLimits)
    objective: str = Field(
        default="technical_limits",
        pattern=r"^(technical_limits|min_power|max_spacing)$",
    )
    optic_families: Optional[list[str]] = None


class TramoDocumentInfo(BaseModel):
    id: int
    filename: str
    document_type: str
    created_at: str


class TramoBody(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    base_name: Optional[str] = Field(default=None, max_length=255)
    variant_name: Optional[str] = Field(default=None, max_length=255)
    parent_section_id: Optional[int] = None
    description: Optional[str] = None
    config_json: Optional[str] = None
    result_json: Optional[str] = None


class LuminaireMaxPowerInfo(BaseModel):
    """Power-cap info for a single 4-tuple ``(gama, difusor, lente, led_type)``.

    Returned by ``GET /api/admin/luminaire-pmax`` so the admin UI can
    audit the cap for any luminaire in the catalog.  ``pmax_ajustada``
    is ``None`` when the LED has no numeric cap recorded (e.g. an
    entry the operator forgot to fill in).
    """

    gama: str
    difusor: str
    lente: str
    led_type: Optional[str] = None
    led_ref: str
    led_desc_corta: Optional[str] = None
    pmax_lum: Optional[float] = None
    pmax_ajustada: Optional[float] = None
    i_max_led: Optional[float] = None


class LedFluxFactorRequest(BaseModel):
    """Body for ``POST /api/ldt/led-flux-factor``.

    The backend derives the factor from the LUXEON 5050 bin table using
    the reference LDT's CCT/CRI and the user's selected CCT/CRI. No data
    is stored; the function is pure.
    """

    ref_cct: int = Field(ge=1800, le=6500)
    ref_cri: int = Field(ge=70, le=90)
    target_cct: int = Field(ge=1800, le=6500)
    target_cri: int = Field(ge=70, le=90)


class LedFluxFactorResponse(BaseModel):
    factor: float


class TramoInfo(BaseModel):
    id: int
    project_id: int
    name: str
    parent_section_id: Optional[int] = None
    base_name: Optional[str] = None
    variant_name: Optional[str] = None
    sort_order: int = 0
    description: Optional[str] = None
    config_json: Optional[str] = None
    result_json: Optional[str] = None
    last_calculated_at: Optional[str] = None
    has_pdf: bool = False
    has_excel: bool = False
    document_ids: dict = Field(default_factory=dict)
    documents: list[TramoDocumentInfo] = Field(default_factory=list)
    compliance_summary: Optional[dict] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class TramoSummary(BaseModel):
    """Lightweight tramo for list views — no config_json / result_json blobs.
    
    ``status`` is computed server-side
    so the frontend can render the table without fetching the full JSON blobs.
    """
    id: int
    project_id: int
    name: str
    parent_section_id: Optional[int] = None
    base_name: Optional[str] = None
    variant_name: Optional[str] = None
    sort_order: int = 0
    description: Optional[str] = None
    last_calculated_at: Optional[str] = None
    has_pdf: bool = False
    has_excel: bool = False
    document_ids: dict = Field(default_factory=dict)
    compliance_summary: Optional[dict] = None
    status: str = "pending"  # dirty | config_error | missing_config | pending | calculation_pending | compliant | non_compliant | no_pcb_capacity
    has_result: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class BulkCalculateProgressItem(BaseModel):
    id: int
    name: str
    status: str  # "pending" | "calculating" | "done" | "error" | "cancelled"
    error: Optional[str] = None
    compliant: Optional[bool] = None


class BulkCalculateStatus(BaseModel):
    batch_id: str
    total: int
    completed: int
    failed: int
    cancelled: bool = False
    items: list[BulkCalculateProgressItem]


class TramoBulkImportItem(BaseModel):
    """One row in a bulk tramo import.

    ``config`` is a raw mapping so the endpoint can validate each row
    individually and report per-row errors without rejecting the whole
    batch. ``name`` is the tramo's display name; when empty the
    server falls back to ``Tramo {row}`` (1-indexed).
    """

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    config: dict


class TramoBulkImportRequest(BaseModel):
    items: list[TramoBulkImportItem] = Field(min_length=1, max_length=5000)
    model_config = ConfigDict(extra="forbid")


class TramoBulkImportResult(BaseModel):
    row: int
    name: str
    status: str  # "created" | "error"
    tramo: Optional[TramoInfo] = None
    error: Optional[str] = None


class TramoBulkImportResponse(BaseModel):
    created: int
    failed: int
    items: list[TramoBulkImportResult]
