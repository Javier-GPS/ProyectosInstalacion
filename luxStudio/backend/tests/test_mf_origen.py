"""Tests for the mf_origen / mf_efectivo wiring in calculator.py.

After the 2026 fix, Salvi LDTs are imported with ``mf_origen=1.0`` (no MF
baked in), so the user-supplied ``config.mf`` is applied verbatim by the
calculator. ``mf_origen<1`` remains supported for the rare third-party
LDT that ships with a depreciation factor already applied.
"""
from app.services.calculator import _effective_mf, _config_to_cfg
from scripts.import_fotometrias_folder import import_folder


def test_catalog_folder_import_defaults_to_raw_photometry():
    """A catalog re-import must not cancel the user maintenance factor."""
    import inspect

    default = inspect.signature(import_folder).parameters["default_mf_origen"].default
    assert default == 1.0


def test_effective_mf_default_catalog_passes_user_mf_through():
    """Catalog LDTs now use mf_origen=1.0, so the user-supplied config.mf
    propagates to the calculation unchanged.
    """
    assert _effective_mf(0.85, {"mf_origen": 1.0}) == 0.85
    assert _effective_mf(0.80, {"mf_origen": 1.0}) == 0.80
    assert _effective_mf(1.0, {"mf_origen": 1.0}) == 1.0


def test_effective_mf_compensates_when_ldt_already_has_mf_baked_in():
    """A third-party LDT with mf_origen=0.85 already has the MF in its cd
    values; the calculator must divide so the total stays at config.mf."""
    value = _effective_mf(0.85, {"mf_origen": 0.85})
    assert value == 1.0  # 0.85 / 0.85
    value = _effective_mf(0.80, {"mf_origen": 0.85})
    assert value == _approx(0.80 / 0.85)
    assert 0.85 * value == _approx(0.80)


def test_effective_mf_handles_missing_metadata():
    """When the LDT row is missing mf_origen, the loader-side default is
    1.0 (raw LDT)."""
    assert _effective_mf(0.85, None) == 0.85
    assert _effective_mf(0.85, {}) == 0.85
    assert _effective_mf(0.80, {"mf_origen": None}) == 0.80


def test_config_to_cfg_uses_effective_mf():
    """_config_to_cfg should expose the effective mf downstream so the
    CIE-140 solver uses the right value."""
    from app.schemas.models import CalculationConfig

    cfg = CalculationConfig(
        road_width=7,
        spacing=30,
        height=9,
        arm_length=1.5,
        pole_side="left",
        optic_family="F151",
        power=100,
        ldt_id="x",
        mf=0.85,
    )

    cfg_raw = _config_to_cfg(cfg, photometry=None, ldt_info={"mf_origen": 1.0})
    assert cfg_raw["mf"] == 0.85

    cfg_baked = _config_to_cfg(cfg, photometry=None, ldt_info={"mf_origen": 0.85})
    assert cfg_baked["mf"] == 1.0

    cfg_no_meta = _config_to_cfg(cfg, photometry=None, ldt_info=None)
    assert cfg_no_meta["mf"] == 0.85


def _approx(value, rel=1e-9):
    class _Approx(float):
        def __new__(cls, v):
            return float.__new__(cls, v)
        def __eq__(self, other):
            return abs(self - other) <= rel
        def __ne__(self, other):
            return not self.__eq__(other)
    return _Approx(value)
