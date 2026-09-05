"""EULUMDAT LDT Parser -- CIE 121:1996.

EULUMDAT line structure (after L7):
  L8  measurement report (text)
  L9  luminaire name (text)
  L10 luminaire number (text -- may be blank)
  L11 file name (text)
  L12 date/user (text)
  L13-L15 luminaire dimensions (3 floats)
  L16-L21 luminous area dims (6 floats)
  L22-L25 DFF, LORL, conversion, tilt (4 floats)
  L26 n_lamp_sets (int)
  For each set: n_lamps(int), lamp_type(text), flux_lm(float),
                CCT(text), CRI(text), W(float)
  10 Direct Ratio values (floats -- skip)
  Mc C-plane angles
  Ng gamma angles
  Mc * Ng intensity values [cd/klm] -> converted to absolute cd on load
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import numpy as np


@dataclass
class Photometry:
    source_file:    str
    manufacturer:   str
    luminaire_name: str
    c_angles: np.ndarray   # shape (Mc,)
    g_angles: np.ndarray   # shape (Ng,)
    _I_matrix: np.ndarray  # shape (Mc, Ng), absolute cd at file flux
    _flux_file_lm: float
    warnings: list = field(default_factory=list)

    def intensity(self, c_deg, gamma_deg, scale_flux_lm=None):
        """Bilinear interpolation of luminous intensity [cd].

        If scale_flux_lm is given, scales from file nominal flux to
        the APHEX operating-point flux.
        """
        c_deg = float(c_deg) % 360.0
        gamma_deg = float(np.clip(gamma_deg, self.g_angles[0], self.g_angles[-1]))
        ci = int(np.clip(np.searchsorted(self.c_angles, c_deg, side="right") - 1,
                         0, len(self.c_angles) - 2))
        gi = int(np.clip(np.searchsorted(self.g_angles, gamma_deg, side="right") - 1,
                         0, len(self.g_angles) - 2))
        c0, c1 = self.c_angles[ci], self.c_angles[ci + 1]
        g0, g1 = self.g_angles[gi], self.g_angles[gi + 1]
        wc = (c_deg - c0) / (c1 - c0) if c1 > c0 else 0.0
        wg = (gamma_deg - g0) / (g1 - g0) if g1 > g0 else 0.0
        I00 = self._I_matrix[ci,     gi    ]
        I10 = self._I_matrix[ci + 1, gi    ]
        I01 = self._I_matrix[ci,     gi + 1]
        I11 = self._I_matrix[ci + 1, gi + 1]
        I_raw = float((1 - wc) * ((1 - wg) * I00 + wg * I01)
                      +     wc * ((1 - wg) * I10 + wg * I11))
        if scale_flux_lm is not None and self._flux_file_lm > 0:
            I_raw *= scale_flux_lm / self._flux_file_lm
        return max(0.0, I_raw)

    def intensity_batch(self, c_deg, gamma_deg, scale_flux_lm=None):
        """
        Vectorized bilinear interpolation — same table lookup as intensity()
        but c_deg/gamma_deg (and scale_flux_lm) may be numpy arrays
        (broadcastable). Returns an ndarray of the broadcast shape.
        """
        c_deg     = np.asarray(c_deg, dtype=float) % 360.0
        gamma_deg = np.clip(np.asarray(gamma_deg, dtype=float),
                            self.g_angles[0], self.g_angles[-1])

        ci = np.searchsorted(self.c_angles, c_deg, side="right") - 1
        ci = np.clip(ci, 0, len(self.c_angles) - 2)
        gi = np.searchsorted(self.g_angles, gamma_deg, side="right") - 1
        gi = np.clip(gi, 0, len(self.g_angles) - 2)

        c0, c1 = self.c_angles[ci], self.c_angles[ci + 1]
        g0, g1 = self.g_angles[gi], self.g_angles[gi + 1]

        dc = c1 - c0
        wc = np.where(dc > 0, (c_deg - c0) / np.where(dc > 0, dc, 1.0), 0.0)
        dg = g1 - g0
        wg = np.where(dg > 0, (gamma_deg - g0) / np.where(dg > 0, dg, 1.0), 0.0)

        I00 = self._I_matrix[ci,     gi    ]
        I10 = self._I_matrix[ci + 1, gi    ]
        I01 = self._I_matrix[ci,     gi + 1]
        I11 = self._I_matrix[ci + 1, gi + 1]

        I_raw = ((1 - wc) * ((1 - wg) * I00 + wg * I01)
                 +     wc * ((1 - wg) * I10 + wg * I11))
        if scale_flux_lm is not None and self._flux_file_lm > 0:
            I_raw = I_raw * (np.asarray(scale_flux_lm, dtype=float) / self._flux_file_lm)
        return np.maximum(0.0, I_raw)

    def reach_distance(self, H, epsilon=0.01, x_min=3.0, x_max_cap=400.0):
        """
        Distancia longitudinal [m] mas alla de la cual esta fotometria deja
        de contribuir de forma apreciable (< epsilon del PICO GLOBAL de la
        fotometria) a la luminancia de un punto -- criterio fisico para
        decidir cuantas luminarias vecinas hace falta considerar en un
        calculo, en vez de una constante fija arbitraria (ver
        optimizer._build_lums/n_side y TunnelCalculator.max_lum_dist).

        IMPORTANTE: el pico de intensidad de una optica vial/tunel tipo
        "batwing" NO suele estar en C=0/180 (el eje longitudinal), sino
        desplazado a un C intermedio (verificado: las 3 opticas Aphex tienen
        su pico entre C=15 y C=30). Comparar solo el plano C=0/180 contra SU
        PROPIO pico local (mas bajo que el pico real) da un criterio
        inconsistente entre opticas -- unas parecen alcanzar mas que otras
        solo por tener el pico mas lejos del eje. Aqui se busca, sobre TODOS
        los planos C tabulados, el mayor gamma en el que la intensidad
        todavia iguala o supera epsilon x pico GLOBAL de toda la fotometria
        (no del plano), y se convierte a distancia con x = H x tan(gamma)
        (geometria de nadir) -- el alcance real, venga de la direccion que
        venga, no solo de la longitudinal.

        H            : altura de montaje [m]
        epsilon      : fraccion del pico global a partir de la cual se
                       considera corte practico (1% por defecto)
        x_min/x_max_cap : cotas de seguridad [m] frente a fotometrias raras
                       o con H extremo (nunca menos de un par de
                       interdistancias tipicas, nunca mas de una distancia
                       ya irrazonable para iluminacion de tunel)
        """
        c_grid, g_grid = np.meshgrid(self.c_angles, self.g_angles, indexing="ij")
        I_all = self.intensity_batch(c_grid, g_grid)  # shape (Mc, Ng)

        I_peak = float(I_all.max())
        if I_peak <= 0:
            return x_min

        above_any_c = (I_all >= epsilon * I_peak).any(axis=0)  # shape (Ng,) — por gamma, ¿algun C llega?
        idx_above = np.where(above_any_c)[0]
        gamma_cutoff = float(self.g_angles[idx_above[-1]]) if len(idx_above) else float(self.g_angles[-1])
        gamma_cutoff = min(gamma_cutoff, 89.5)  # evitar tan(90°) = infinito

        x = float(H) * math.tan(math.radians(gamma_cutoff))
        return float(np.clip(x, x_min, x_max_cap))

    def normalized_intensity(self, c_deg, gamma_deg):
        """Return intensity normalised to 1 klm [cd/klm]."""
        if self._flux_file_lm <= 0:
            return self.intensity(c_deg, gamma_deg)
        return self.intensity(c_deg, gamma_deg) / (self._flux_file_lm / 1000.0)

    def total_flux_lm(self):
        """Compute total luminous flux [lm] by numerical integration."""
        I_avg = np.mean(self._I_matrix, axis=0)
        g_rad = np.deg2rad(self.g_angles)
        return max(0.0, 2 * math.pi * float(np.trapz(I_avg * np.sin(g_rad), g_rad)))

    def optic_id(self):
        """Extract short optic identifier from source filename."""
        parts = Path(self.source_file).stem.split("_")
        for p in parts:
            if p.startswith("F") and len(p) >= 3:
                return p
        return Path(self.source_file).stem


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse_ldt(path, encoding="latin-1"):
    """Parse a EULUMDAT .ldt file and return a Photometry object.

    Key design decisions:
    - L8-L12 are text fields (some may be blank) -- read by exact line index.
    - Numeric sections use a blank-skipping reader.
    - 10 Direct Ratio values after lamp sets are read and discarded.
    - Raw intensity values (cd/klm) are converted to absolute cd on load.
    """
    path = Path(path)
    raw = path.read_bytes().decode(encoding, errors="replace").replace("\x00", "")
    lines = [ln.rstrip() for ln in raw.splitlines()]
    warnings = []
    idx = 0

    def _read():
        """Read exactly one line (may be blank)."""
        nonlocal idx
        if idx < len(lines):
            ln = lines[idx]; idx += 1
            return ln.strip()
        return ""

    def _nxt():
        """Read next non-blank line."""
        nonlocal idx
        while idx < len(lines):
            ln = lines[idx]; idx += 1
            if ln.strip():
                return ln.strip()
        return ""

    def _f(s):
        return float(s.strip().replace(",", "."))

    # L1-L7: always non-blank -- use _nxt
    manufacturer = _nxt()
    ityp = int(_nxt())
    isym = int(_nxt())
    Mc   = int(_nxt())
    Dc   = _f(_nxt())
    Ng   = int(_nxt())
    Dg   = _f(_nxt())

    # L8-L12: text fields -- read by exact line (L10 may be blank)
    _read()                     # L8  measurement report
    luminaire_name = _read()    # L9  luminaire name
    _read()                     # L10 luminaire number (often blank)
    _read()                     # L11 file name
    _read()                     # L12 date/user

    # L13-L15: luminaire dimensions
    _nxt(); _nxt(); _nxt()

    # L16-L21: luminous area dimensions (6 values)
    for _ in range(6):
        _nxt()

    # L22-L25: DFF, LORL, conversion factor, tilt
    _nxt(); _nxt(); _nxt(); _nxt()

    # L26: number of lamp sets
    n_lamp_sets = int(_f(_nxt()))

    flux_file_lm = 0.0
    for _ in range(n_lamp_sets):
        n_lamps  = int(_f(_nxt()))  # lamps in set
        _nxt()                       # lamp type (text)
        lm_line  = _nxt()            # luminous flux [lm]
        _nxt(); _nxt(); _nxt()       # CCT, CRI, W
        try:
            flux_file_lm += n_lamps * _f(lm_line)
        except ValueError:
            warnings.append(f"Could not parse lamp flux: '{lm_line}'")

    if flux_file_lm <= 0:
        warnings.append("Lamp flux zero/missing -- normalisation disabled.")

    # 10 Direct Ratio (DR) values -- present in EULUMDAT after lamp sets; skip
    dr_read = []
    while len(dr_read) < 10:
        tok = _nxt()
        for t in tok.split():
            try:
                dr_read.append(_f(t))
            except ValueError:
                pass
            if len(dr_read) == 10:
                break

    # Mc C-plane angles
    c_raw = []
    while len(c_raw) < Mc:
        tok = _nxt()
        for t in tok.split():
            try:
                c_raw.append(_f(t))
            except ValueError:
                pass
            if len(c_raw) == Mc:
                break

    # Ng gamma angles
    g_raw = []
    while len(g_raw) < Ng:
        tok = _nxt()
        for t in tok.split():
            try:
                g_raw.append(_f(t))
            except ValueError:
                pass
            if len(g_raw) == Ng:
                break

    # Mc * Ng intensity values
    total = Mc * Ng
    I_flat = []
    while len(I_flat) < total:
        tok = _nxt()
        if not tok:
            break
        for t in tok.split():
            try:
                I_flat.append(_f(t))
            except ValueError:
                pass
            if len(I_flat) == total:
                break

    if len(I_flat) < total:
        warnings.append(f"Expected {total} intensity values, got {len(I_flat)}. Padding.")
        I_flat += [0.0] * (total - len(I_flat))

    I_mat = np.array(I_flat[:total], dtype=float).reshape(Mc, Ng)

    # EULUMDAT stores intensities in cd/klm -- convert to absolute cd
    if flux_file_lm > 0:
        I_mat = I_mat * (flux_file_lm / 1000.0)

    c_angles, I_matrix = _expand_symmetry(isym, c_raw, g_raw, I_mat, warnings)

    if np.any(I_matrix < 0):
        I_matrix = np.clip(I_matrix, 0.0, None)

    return Photometry(
        source_file    = str(path),
        manufacturer   = manufacturer,
        luminaire_name = luminaire_name,
        c_angles       = np.array(c_angles, dtype=float),
        g_angles       = np.array(g_raw, dtype=float),
        _I_matrix      = I_matrix,
        _flux_file_lm  = flux_file_lm,
        warnings       = warnings,
    )


def _expand_symmetry(isym, c_list, g_list, I_raw, warnings):
    """Expand partial C-plane dataset to full 0-360 degrees.

    isym codes (EULUMDAT / CIE 121):
      0 = no symmetry (full data provided)
      1 = symmetry about C0-C180 plane
      2 = symmetry about C90-C270 plane
      3 = quarter symmetry (C0 and C90 axes)
      4 = rotational symmetry
    """
    Ng = len(g_list)
    if isym == 0:
        return c_list, I_raw

    step = (c_list[1] - c_list[0]) if len(c_list) > 1 else 15.0
    n_full = int(round(360.0 / step))
    full_c = [i * step for i in range(n_full)]
    I_full = np.zeros((n_full, Ng), dtype=float)

    def _interp(c):
        c = float(c) % 360.0
        ci = int(np.clip(np.searchsorted(c_list, c, side="right") - 1,
                         0, len(c_list) - 2))
        c0, c1 = c_list[ci], c_list[ci + 1]
        w = (c - c0) / (c1 - c0) if c1 > c0 else 0.0
        return (1 - w) * I_raw[ci] + w * I_raw[ci + 1]

    for i, c in enumerate(full_c):
        if   isym == 4: I_full[i] = I_raw[0]
        elif isym == 1: I_full[i] = _interp(c if c <= 180.0 else 360.0 - c)
        elif isym == 2:
            if   c <= 90:  I_full[i] = _interp(c)
            elif c <= 180: I_full[i] = _interp(180.0 - c)
            elif c <= 270: I_full[i] = _interp(c - 180.0)
            else:          I_full[i] = _interp(360.0 - c)
        elif isym == 3: I_full[i] = _interp(c % 90.0)
        else:
            warnings.append(f"Unknown isym={isym}; treating as no symmetry.")
            I_full[i] = _interp(c)

    return full_c, I_full


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_CACHE: dict = {}


def load_ldt(path):
    """Parse and cache a LDT file (keyed by resolved absolute path)."""
    key = str(Path(path).resolve())
    if key not in _CACHE:
        _CACHE[key] = parse_ldt(path)
    return _CACHE[key]
