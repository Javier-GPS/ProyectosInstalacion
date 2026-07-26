"""Thermal slope table and difusor code mapping for the V2 LED model.

``TABLA_TS_SLOPE`` is the slope_LED per (gama, dif_code) from the
motor_configurador Datos sheet.  ``dif_code`` maps a difusor name to
the short code used as the table key.
"""

DEFAULT_DIF_CODE = "S"

# slope_LED per (gama, dif_code).  ponytail: only covers gamas present
# in Configurador Datos; unknown combos fall back to 0.3.
TABLA_TS_SLOPE: dict[tuple[str, str], float] = {
    ("CLAP M", "S"): 0.24,  ("CLAP M", "W"): 0.2,
    ("CLAP S", "S"): 0.532, ("CLAP S", "W"): 0.509,
    ("BASIC S", "S"): 0.567, ("BASIC S", "W"): 0.572,
    ("TUBO S", "S"): 0.310, ("TUBO S", "W"): 0.351,
    ("TUBO M", "S"): 0.263,  ("TUBO M", "W"): 0.243,
    ("CLAP L", "S"): 0.323, ("CLAP L", "W"): 0.288,
    ("SIL M", "S"): 0.448, ("SIL M", "W"): 0.346,
    ("GOTA S", "S"): 0.497,
    ("WIN S", "S"): 0.415, ("WIN S", "W"): 0.331,
    ("ICU S", "S"): 1.056, ("ICU S", "W"): 0.826,
    ("NEREA S", "S"): 0.485, ("NEREA S", "W"): 0.577,
    ("ATENEA S", "S"): 0.810, ("ATENEA S", "W"): 0.922,
    ("ATENEA M", "S"): 0.413, ("ATENEA M", "W"): 0.371,
    ("ION S", "S"): 0.653,
    ("NEMO S", "S"): 0.294, ("NEMO S", "W"): 0.293,
    ("CDP S", "S"): 0.542, ("CDP S", "W"): 0.668,
    ("LOOM S", "S"): 0.401, ("LOOM S", "W"): 0.359,
    ("PUCK S", "S"): 0.407, ("PUCK S", "W"): 0.359,
    ("HOOP S", "S"): 0.200, ("HOOP S", "W"): 0.200,
    ("TAPA M", "S"): 0.383, ("TAPA M", "W"): 0.361,
    ("PUCK M", "S"): 0.390, ("PUCK M", "W"): 0.367,
    ("TUBO L", "S"): 0.237, ("TUBO L", "W"): 0.233,
    ("TUBO XL", "S"): 0.196, ("TUBO XL", "W"): 0.194,
    ("GOTA M", "S"): 0.312,
    ("BASIC M", "S"): 0.316,
    ("PUCK L", "S"): 0.288, ("PUCK L", "W"): 0.274,
    ("PUCK XL", "S"): 0.235, ("PUCK XL", "W"): 0.225,
    ("WIN M", "S"): 0.254, ("WIN M", "W"): 0.219,
}


def dif_code(difusor_name: str | None) -> str:
    """Map difusor name to short code used in TABLA_TS.

    "S" for VDR SPUW-like, "W" for PMMA A-like; defaults to "S".
    """
    if not difusor_name:
        return DEFAULT_DIF_CODE
    n = difusor_name.strip().upper()
    if "PMMA" in n or "AC" in n or "PMMA A" in n or "PL" in n:
        return "W"
    if "SPUW" in n or "VDR SPUW" in n or "3W" in n:
        return "S"
    return DEFAULT_DIF_CODE
