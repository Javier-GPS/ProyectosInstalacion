"""LUXEON 5050 CRI/CCT flux ratio helper for the V2 LED model."""

from typing import Optional

from .interpolate import interpolate


# LUXEON 5050 Round typical luminous flux at rated current, Tj=25 C.
# Values are normalized against CRI 70 by CCT and interpolated for intermediate CCTs.
LUXEON_5050_CRI_FLUX: dict[int, dict[int, float]] = {
    2700: {70: 640.0, 80: 593.0, 90: 475.0},
    3000: {70: 667.0, 80: 615.0, 90: 490.0},
    3500: {70: 686.0, 80: 620.0, 90: 510.0},
    4000: {70: 693.0, 80: 645.0, 90: 530.0},
    5000: {70: 693.0, 80: 645.0, 90: 530.0},
    5700: {70: 683.0, 80: 644.0, 90: 530.0},
}


def led_flux_factor(
    target_cct: int,
    target_cri: int,
    reference_cct: int = 4000,
    reference_cri: int = 70,
) -> float:
    """LED flux ratio for target CCT/CRI against the reference LDT.

    DIALux applies the selected luminaire flux for the actual CCT as
    well, so a 3000 K calculation using a 4000 K reference photometry
    must be scaled by the LED flux ratio between those two bins.
    """
    target_cri = min(90, max(70, int(target_cri)))
    reference_cri = min(90, max(70, int(reference_cri)))

    def flux_for_cri(values: dict[int, float], cri: int) -> Optional[float]:
        return interpolate(float(cri), [(float(key), value) for key, value in values.items()])

    def flux_for(cct: int, cri: int) -> Optional[float]:
        points = [
            (float(cct_value), flux_for_cri(values, cri))
            for cct_value, values in LUXEON_5050_CRI_FLUX.items()
        ]
        points = [(cct_value, flux) for cct_value, flux in points if flux is not None]
        return interpolate(float(cct), points)

    target_flux = flux_for(target_cct, target_cri)
    reference_flux = flux_for(reference_cct, reference_cri)
    if not target_flux or not reference_flux:
        return 1.0
    return target_flux / reference_flux
