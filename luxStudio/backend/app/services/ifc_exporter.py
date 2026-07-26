"""IFC 4.3 exporter for DIALux evo interop.

Generates an IFC file (IFC4X3_ADD2) that DIALux evo 7+ can import via
its IFC import function. The file mirrors the CIE 140 calculation
results so a third party can re-derive the photometric numbers in any
compliant BIM tool.

Geometry layout
---------------
We build a simple linear street:

    IfcProject
      └── IfcSite
            └── IfcFacility (Road)
                  └── IfcFacilityPart (Carriageway)
                  └── IfcLightFixture × N  (per pole, with maintenance factor)

Coordinates:
    * x = along the road (pole positions at multiples of spacing S)
    * y = across the road (y=0 = left edge of carriageway, y=W = right)
    * z = up (z=h = luminaire mounting height)

The pole baseline runs along x at y = arm offset on the chosen side.

IFC4X3_ADD2 notes
-----------------
* `IfcLightFixtureTypeEnum` and `IfcLightFixture.PredefinedType` only
  accept `USERDEFINED` / `NOTDEFINED` in IFC4X3_ADD2. The mounting
  type is conveyed through `Pset_LightFixtureTypeCommon.
  LightFixtureMountingType = "POLE_MOUNTED"` (still standard).
* `IfcRoadMarking` is not in IFC4X3_ADD2; we draw pole baselines as
  `IfcPavement` cylinders instead.
* `IfcFacilityPart` only exposes `UsageType` (VERTICAL/HORIZONTAL/...)
  and has no `PredefinedType` here.
* `Dimensions` on `IfcSIUnit` is derived; pass only `UnitType`,
  `Prefix`, `Name`.
* `MaintenanceFactor` is set on the property set so DIALux evo applies
  the same MF the CIE 140 calculation used.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

import ifcopenshell
from ifcopenshell import file as ifc_file
from ifcopenshell.guid import compress

from ..schemas.models import CalculationConfig, CalculationResult, FotometriaInfo

log = logging.getLogger(__name__)

_POLE_PERIODS = 3
_HALF_DEPTH = 0.025
_MARKER_RADIUS = 0.05
_MARKER_HEIGHT = 0.01
_POLE_HANDLE_RADIUS = 0.04
_POLE_HANDLE_HEIGHT = 0.4


def _guid() -> str:
    return compress(str(uuid.uuid4()))


def _axis2_2d(file: ifc_file):
    return file.createIfcAxis2Placement2D(
        file.createIfcCartesianPoint((0.0, 0.0))
    )


def _axis2_3d(file: ifc_file):
    return file.createIfcAxis2Placement3D(
        file.createIfcCartesianPoint((0.0, 0.0, 0.0)),
        file.createIfcDirection((0.0, 0.0, 1.0)),
        file.createIfcDirection((1.0, 0.0, 0.0)),
    )


def _pole_positions(config: CalculationConfig) -> list[tuple[float, float, float]]:
    W = float(config.road_width)
    arm = float(config.arm_length)
    pole_side = (config.pole_side or "left").lower()
    baseline_y = W - arm if pole_side == "right" else arm
    h = float(config.height)
    S = float(config.spacing)
    return [(k * S, baseline_y, h) for k in range(-_POLE_PERIODS, _POLE_PERIODS + 1)]


def _extruded_shape(file: ifc_file, context, profile, position, direction, depth):
    solid = file.createIfcExtrudedAreaSolid(
        SweptArea=profile,
        Position=position,
        ExtrudedDirection=direction,
        Depth=depth,
    )
    rep = file.createIfcShapeRepresentation(
        ContextOfItems=context,
        RepresentationIdentifier="Body",
        RepresentationType="SolidModel",
        Items=[solid],
    )
    return file.createIfcProductDefinitionShape(
        Name=None, Description=None, Representations=[rep]
    )


def _pole_handle_shape(file: ifc_file, context):
    profile = file.createIfcCircleProfileDef(
        ProfileType="AREA",
        ProfileName=None,
        Position=_axis2_2d(file),
        Radius=_POLE_HANDLE_RADIUS,
    )
    direction = file.createIfcDirection((0.0, 0.0, 1.0))
    position = _axis2_3d(file)
    return _extruded_shape(
        file, context, profile, position, direction, _POLE_HANDLE_HEIGHT
    )


def _make_pole_baseline_shape(file: ifc_file, context):
    profile = file.createIfcCircleProfileDef(
        ProfileType="AREA",
        ProfileName=None,
        Position=_axis2_2d(file),
        Radius=_MARKER_RADIUS,
    )
    direction = file.createIfcDirection((0.0, 0.0, 1.0))
    position = _axis2_3d(file)
    return _extruded_shape(
        file, context, profile, position, direction, _MARKER_HEIGHT
    )


def _make_owner_history(file: ifc_file):
    organization = file.createIfcOrganization(
        Identification="luxStudio", Name="luxStudio", Description=None, Roles=None
    )
    person = file.createIfcPerson(
        Identification="lux",
        FamilyName="Studio",
        GivenName=None,
        MiddleNames=None,
        PrefixTitles=None,
        SuffixTitles=None,
        Roles=None,
        Addresses=None,
    )
    p_o = file.createIfcPersonAndOrganization(
        ThePerson=person, TheOrganization=organization, Roles=None
    )
    app = file.createIfcApplication(
        ApplicationDeveloper=organization,
        Version="0.1",
        ApplicationFullName="luxStudio",
        ApplicationIdentifier="luxStudio",
    )
    return file.createIfcOwnerHistory(
        p_o,
        app,
        None,
        "NOTDEFINED",
        None,
        None,
        None,
        0,
    )


def _build_units(file: ifc_file):
    return file.createIfcUnitAssignment(Units=[
        file.createIfcSIUnit(UnitType="LENGTHUNIT", Prefix=None, Name="METRE"),
        file.createIfcSIUnit(UnitType="AREAUNIT", Prefix=None, Name="SQUARE_METRE"),
        file.createIfcSIUnit(UnitType="VOLUMEUNIT", Prefix=None, Name="CUBIC_METRE"),
        file.createIfcSIUnit(UnitType="PLANEANGLEUNIT", Prefix=None, Name="RADIAN"),
        file.createIfcSIUnit(UnitType="SOLIDANGLEUNIT", Prefix=None, Name="STERADIAN"),
        file.createIfcSIUnit(UnitType="LUMINOUSFLUXUNIT", Prefix=None, Name="LUMEN"),
        file.createIfcSIUnit(UnitType="LUMINOUSINTENSITYUNIT", Prefix=None, Name="CANDELA"),
        file.createIfcSIUnit(UnitType="ILLUMINANCEUNIT", Prefix=None, Name="LUX"),
        file.createIfcSIUnit(UnitType="POWERUNIT", Prefix=None, Name="WATT"),
    ])


def _build_geometry_contexts(file: ifc_file):
    context_3d = file.createIfcGeometricRepresentationContext(
        ContextIdentifier=None,
        ContextType="Model",
        CoordinateSpaceDimension=3,
        Precision=1.0e-5,
        WorldCoordinateSystem=_axis2_3d(file),
        TrueNorth=None,
    )
    file.createIfcGeometricRepresentationSubContext(
        ContextIdentifier="Body",
        ContextType="Model",
        ParentContext=context_3d,
        TargetView="MODEL_VIEW",
    )
    return context_3d


def _add_carriageway_slab(
    file: ifc_file, history, context, parent_placement, config: CalculationConfig
):
    W = float(config.road_width)
    L = float(config.spacing) * (2 * _POLE_PERIODS)
    slab_thickness = 0.05

    profile = file.createIfcRectangleProfileDef(
        ProfileType="AREA",
        ProfileName=None,
        Position=_axis2_2d(file),
        XDim=W,
        YDim=slab_thickness,
    )
    direction = file.createIfcDirection((1.0, 0.0, 0.0))
    position = file.createIfcAxis2Placement3D(
        Location=file.createIfcCartesianPoint((-L / 2, 0.0, -slab_thickness)),
        Axis=file.createIfcDirection((0.0, 0.0, 1.0)),
        RefDirection=file.createIfcDirection((1.0, 0.0, 0.0)),
    )
    shape = _extruded_shape(file, context, profile, position, direction, L)
    placement = file.createIfcLocalPlacement(
        PlacementRelTo=parent_placement, RelativePlacement=_axis2_3d(file)
    )
    return file.createIfcSlab(
        GlobalId=_guid(),
        OwnerHistory=history,
        Name="Carriageway Slab",
        Description=None,
        ObjectType=None,
        ObjectPlacement=placement,
        Representation=shape,
        Tag=None,
        PredefinedType="FLOOR",
    )


def _add_pole_baseline_markers(
    file: ifc_file, history, context, parent_placement, config: CalculationConfig
):
    S = float(config.spacing)
    shape = _make_pole_baseline_shape(file, context)
    markers = []
    for k in range(-_POLE_PERIODS, _POLE_PERIODS + 1):
        x = k * S
        placement = file.createIfcLocalPlacement(
            PlacementRelTo=parent_placement,
            RelativePlacement=file.createIfcAxis2Placement3D(
                Location=file.createIfcCartesianPoint((x, 0.0, 0.0)),
                Axis=file.createIfcDirection((0.0, 0.0, 1.0)),
                RefDirection=file.createIfcDirection((1.0, 0.0, 0.0)),
            ),
        )
        marker = file.createIfcPavement(
            GlobalId=_guid(),
            OwnerHistory=history,
            Name=f"Pole baseline x={x:.1f}m",
            Description=None,
            ObjectType=None,
            ObjectPlacement=placement,
            Representation=shape,
            Tag=None,
            PredefinedType="USERDEFINED",
        )
        markers.append(marker)
    return markers


def _add_light_fixture_type(
    file: ifc_file, history, config: CalculationConfig, lum: FotometriaInfo
):
    light_type = file.createIfcLightFixtureType(
        GlobalId=_guid(),
        OwnerHistory=history,
        Name=f"{lum.luminaire_name} {int(lum.power)}W",
        Description=None,
        ApplicableOccurrence=None,
        HasPropertySets=None,
        RepresentationMaps=None,
        Tag=None,
        ElementType=None,
        PredefinedType="USERDEFINED",
    )

    pset_common = file.createIfcPropertySet(
        GlobalId=_guid(),
        OwnerHistory=history,
        Name="Pset_LightFixtureTypeCommon",
        Description=None,
        HasProperties=[
            file.createIfcPropertySingleValue(
                Name="NumberOfSources",
                Specification=None,
                NominalValue=file.createIfcInteger(1),
                Unit=None,
            ),
            file.createIfcPropertySingleValue(
                Name="TotalWattage",
                Specification=None,
                NominalValue=file.createIfcReal(lum.power),
                Unit=None,
            ),
            file.createIfcPropertySingleValue(
                Name="LightFixtureMountingType",
                Specification=None,
                NominalValue=file.createIfcLabel("POLE_MOUNTED"),
                Unit=None,
            ),
            file.createIfcPropertySingleValue(
                Name="MaintenanceFactor",
                Specification=None,
                NominalValue=file.createIfcReal(config.mf),
                Unit=None,
            ),
        ],
    )
    pset_elec = file.createIfcPropertySet(
        GlobalId=_guid(),
        OwnerHistory=history,
        Name="Pset_ElectricalDeviceCommon",
        Description=None,
        HasProperties=[
            file.createIfcPropertySingleValue(
                Name="Power",
                Specification=None,
                NominalValue=file.createIfcReal(lum.power),
                Unit=None,
            ),
            file.createIfcPropertySingleValue(
                Name="NominalPowerConsumption",
                Specification=None,
                NominalValue=file.createIfcReal(lum.power),
                Unit=None,
            ),
        ],
    )
    pset_manu = file.createIfcPropertySet(
        GlobalId=_guid(),
        OwnerHistory=history,
        Name="Pset_ManufacturerTypeInformation",
        Description=None,
        HasProperties=[
            file.createIfcPropertySingleValue(
                Name="Manufacturer",
                Specification=None,
                NominalValue=file.createIfcLabel(lum.manufacturer),
                Unit=None,
            ),
            file.createIfcPropertySingleValue(
                Name="ModelReference",
                Specification=None,
                NominalValue=file.createIfcLabel(lum.luminaire_name),
                Unit=None,
            ),
        ],
    )
    file.createIfcRelDefinesByProperties(
        GlobalId=_guid(),
        OwnerHistory=history,
        Name=None,
        Description=None,
        RelatedObjects=[light_type],
        RelatingPropertyDefinition=pset_common,
    )
    file.createIfcRelDefinesByProperties(
        GlobalId=_guid(),
        OwnerHistory=history,
        Name=None,
        Description=None,
        RelatedObjects=[light_type],
        RelatingPropertyDefinition=pset_elec,
    )
    file.createIfcRelDefinesByProperties(
        GlobalId=_guid(),
        OwnerHistory=history,
        Name=None,
        Description=None,
        RelatedObjects=[light_type],
        RelatingPropertyDefinition=pset_manu,
    )
    return light_type


def _add_light_fixtures(
    file: ifc_file,
    history,
    light_type,
    parent_placement,
    context,
    config: CalculationConfig,
):
    positions = _pole_positions(config)
    tilt_deg = float(config.tilt)
    arm_len = float(config.arm_length)
    fixture_shape = _pole_handle_shape(file, context)
    instances = []
    for x, y, z in positions:
        placement = file.createIfcLocalPlacement(
            PlacementRelTo=parent_placement,
            RelativePlacement=file.createIfcAxis2Placement3D(
                Location=file.createIfcCartesianPoint((x, y, z)),
                Axis=file.createIfcDirection((0.0, 0.0, 1.0)),
                RefDirection=file.createIfcDirection((1.0, 0.0, 0.0)),
            ),
        )
        fixture = file.createIfcLightFixture(
            GlobalId=_guid(),
            OwnerHistory=history,
            Name=f"Luminaire @ x={x:.1f}m",
            Description=None,
            ObjectType=None,
            ObjectPlacement=placement,
            Representation=fixture_shape,
            Tag=None,
            PredefinedType="USERDEFINED",
        )
        instances.append(fixture)

        pset_occ = file.createIfcPropertySet(
            GlobalId=_guid(),
            OwnerHistory=history,
            Name="Pset_LightFixtureCommon",
            Description=None,
            HasProperties=[
                file.createIfcPropertySingleValue(
                    Name="MountingHeight",
                    Specification=None,
                    NominalValue=file.createIfcReal(config.height),
                    Unit=None,
                ),
                file.createIfcPropertySingleValue(
                    Name="ArmLength",
                    Specification=None,
                    NominalValue=file.createIfcReal(arm_len),
                    Unit=None,
                ),
                file.createIfcPropertySingleValue(
                    Name="ArmTiltAngle",
                    Specification=None,
                    NominalValue=file.createIfcReal(tilt_deg),
                    Unit=None,
                ),
                file.createIfcPropertySingleValue(
                    Name="MaintenanceFactor",
                    Specification=None,
                    NominalValue=file.createIfcReal(config.mf),
                    Unit=None,
                ),
            ],
        )
        file.createIfcRelDefinesByProperties(
            GlobalId=_guid(),
            OwnerHistory=history,
            Name=None,
            Description=None,
            RelatedObjects=[fixture],
            RelatingPropertyDefinition=pset_occ,
        )
    file.createIfcRelDefinesByType(
        GlobalId=_guid(),
        OwnerHistory=history,
        Name=None,
        Description=None,
        RelatedObjects=instances,
        RelatingType=light_type,
    )
    return instances


def build_ifc(
    config: CalculationConfig,
    result: CalculationResult,
    luminaire: FotometriaInfo,
    output: Path,
) -> Path:
    """Write a DIALux-evo-compatible IFC4X3 file at ``output``."""
    file = ifcopenshell.file(schema="IFC4X3_ADD2")
    history = _make_owner_history(file)

    project = file.createIfcProject(
        GlobalId=_guid(),
        OwnerHistory=history,
        Name="luxStudio Street Lighting Project",
        Description=None,
        ObjectType=None,
        LongName=None,
        Phase=None,
        RepresentationContexts=None,
        UnitsInContext=_build_units(file),
    )

    context_3d = _build_geometry_contexts(file)
    project.RepresentationContexts = [context_3d]

    site_placement = file.createIfcLocalPlacement(
        PlacementRelTo=None, RelativePlacement=_axis2_3d(file)
    )
    site = file.createIfcSite(
        GlobalId=_guid(),
        OwnerHistory=history,
        Name="Road Site",
        Description=None,
        ObjectType=None,
        ObjectPlacement=site_placement,
        Representation=None,
        LongName=None,
        CompositionType="ELEMENT",
        RefLatitude=None,
        RefLongitude=None,
        RefElevation=None,
        LandTitleNumber=None,
        SiteAddress=None,
    )
    file.createIfcRelAggregates(
        GlobalId=_guid(),
        OwnerHistory=history,
        Name=None,
        Description=None,
        RelatingObject=project,
        RelatedObjects=[site],
    )

    facility_placement = file.createIfcLocalPlacement(
        PlacementRelTo=site_placement, RelativePlacement=_axis2_3d(file)
    )
    facility = file.createIfcFacility(
        GlobalId=_guid(),
        OwnerHistory=history,
        Name="Road",
        Description=None,
        ObjectType=None,
        ObjectPlacement=facility_placement,
        Representation=None,
        LongName=None,
        CompositionType="ELEMENT",
    )
    file.createIfcRelAggregates(
        GlobalId=_guid(),
        OwnerHistory=history,
        Name=None,
        Description=None,
        RelatingObject=site,
        RelatedObjects=[facility],
    )

    carriageway_placement = file.createIfcLocalPlacement(
        PlacementRelTo=facility_placement, RelativePlacement=_axis2_3d(file)
    )
    carriageway = file.createIfcFacilityPart(
        GlobalId=_guid(),
        OwnerHistory=history,
        Name="Carriageway",
        Description=None,
        ObjectType=None,
        ObjectPlacement=carriageway_placement,
        Representation=None,
        LongName=None,
        CompositionType="ELEMENT",
        UsageType="VERTICAL",
    )
    file.createIfcRelAggregates(
        GlobalId=_guid(),
        OwnerHistory=history,
        Name=None,
        Description=None,
        RelatingObject=facility,
        RelatedObjects=[carriageway],
    )

    slab = _add_carriageway_slab(file, history, context_3d, facility_placement, config)
    markers = _add_pole_baseline_markers(
        file, history, context_3d, facility_placement, config
    )
    light_type = _add_light_fixture_type(file, history, config, luminaire)
    fixtures = _add_light_fixtures(
        file, history, light_type, facility_placement, context_3d, config
    )

    file.createIfcRelContainedInSpatialStructure(
        GlobalId=_guid(),
        OwnerHistory=history,
        Name=None,
        Description=None,
        RelatedElements=[carriageway, slab, *markers, *fixtures],
        RelatingStructure=facility,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    file.write(str(output))
    log.info("Wrote IFC file with %d luminaires to %s", len(fixtures), output)
    return output
