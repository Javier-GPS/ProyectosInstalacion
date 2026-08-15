"""Small, dependency-free EULUMDAT reader and writer.

The input LDT is kept as an absolute photometric shape in cd/klm. Runtime
scaling is always performed from the declared reference flux, as required by
the existing SALVI calculation engines.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path


class LdtError(ValueError):
    """Raised when an LDT is malformed or cannot be represented."""


def _number(value: str, field_name: str) -> float:
    try:
        return float(value.strip().replace(",", "."))
    except ValueError as exc:
        raise LdtError(f"Invalid {field_name}: {value!r}") from exc


def _integer(value: str, field_name: str) -> int:
    try:
        return int(value.strip())
    except ValueError as exc:
        raise LdtError(f"Invalid {field_name}: {value!r}") from exc


def _line(lines: list[str], index: int, field_name: str) -> str:
    if index >= len(lines):
        raise LdtError(f"Missing {field_name} at line {index + 1}")
    return lines[index].strip()


@dataclass(frozen=True)
class LampSet:
    number_of_lamps: str
    lamp_type: str
    flux_lm: float
    color: str
    cri: str
    wattage_w: float


@dataclass
class LdtPhotometry:
    """Parsed full-grid LDT photometry."""

    company: str
    name: str
    c_angles_deg: list[float]
    gamma_angles_deg: list[float]
    intensities_cd_per_klm: list[list[float]]
    lamp_sets: list[LampSet]
    symmetry: int = 0
    conversion: float = 1.0
    lorl_percent: float = 100.0
    dimensions_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def flux_lm(self) -> float:
        return sum(item.flux_lm for item in self.lamp_sets)

    @property
    def power_w(self) -> float:
        return sum(item.wattage_w for item in self.lamp_sets)

    def validate(self) -> None:
        if len(self.c_angles_deg) != len(self.intensities_cd_per_klm):
            raise LdtError("C axis and intensity matrix have different sizes")
        if len(self.c_angles_deg) < 2 or len(self.gamma_angles_deg) < 2:
            raise LdtError("LDT requires at least two C and gamma samples")
        if any(b <= a for a, b in zip(self.c_angles_deg, self.c_angles_deg[1:])):
            raise LdtError("C angles must be strictly increasing")
        if any(b <= a for a, b in zip(self.gamma_angles_deg, self.gamma_angles_deg[1:])):
            raise LdtError("gamma angles must be strictly increasing")
        if any(len(row) != len(self.gamma_angles_deg) for row in self.intensities_cd_per_klm):
            raise LdtError("Intensity matrix does not match gamma axis")
        if any(value < 0 or not math.isfinite(value) for row in self.intensities_cd_per_klm for value in row):
            raise LdtError("LDT intensities must be finite and non-negative")
        if self.symmetry not in (0, 1, 2, 3, 4):
            raise LdtError("Unsupported EULUMDAT symmetry code")

    def _c_axis_is_circular(self) -> bool:
        """Return whether the C grid covers a complete 360 degree turn."""
        if len(self.c_angles_deg) < 2:
            return False
        step = self.c_angles_deg[1] - self.c_angles_deg[0]
        return self.c_angles_deg[-1] - self.c_angles_deg[0] + step >= 360.0 - 1e-6

    def intensity_cd_per_klm(self, c_deg: float, gamma_deg: float) -> float:
        """Bilinearly interpolate the full expanded matrix."""
        self.validate()
        gamma = max(0.0, min(180.0, float(gamma_deg)))
        # An LDT with no upper-hemisphere samples cannot provide a physical
        # value for gamma > 90. Returning zero is safer than duplicating the
        # nadir hemisphere and it keeps TI non-certifiable through diagnostics.
        if gamma > self.gamma_angles_deg[-1]:
            return 0.0
        c = float(c_deg) % 360.0
        c_axis = self.c_angles_deg
        circular_c = self._c_axis_is_circular()
        if not circular_c and (c < c_axis[0] or c > c_axis[-1]):
            # A half-plane LDT is directional. Do not close C=180 to C=0.
            return 0.0
        if circular_c and c < c_axis[0]:
            c += 360.0

        def bracket(axis: list[float], value: float, circular: bool = False) -> tuple[int, int, float]:
            if circular and value >= axis[-1]:
                step = (axis[1] - axis[0]) if len(axis) > 1 else 360.0
                upper = axis[0] + 360.0
                weight = (value - axis[-1]) / (upper - axis[-1])
                return len(axis) - 1, 0, weight
            if value <= axis[0]:
                return 0, 1, 0.0
            for index in range(len(axis) - 1):
                if axis[index] <= value <= axis[index + 1]:
                    span = axis[index + 1] - axis[index]
                    return index, index + 1, (value - axis[index]) / span
            return len(axis) - 2, len(axis) - 1, 1.0

        c0, c1, wc = bracket(c_axis, c, circular=circular_c)
        g0, g1, wg = bracket(self.gamma_angles_deg, gamma)
        a = self.intensities_cd_per_klm[c0][g0]
        b = self.intensities_cd_per_klm[c0][g1]
        d = self.intensities_cd_per_klm[c1][g0]
        e = self.intensities_cd_per_klm[c1][g1]
        value = (1 - wc) * ((1 - wg) * a + wg * b) + wc * ((1 - wg) * d + wg * e)
        return max(0.0, value * self.conversion)


def ldt_diagnostic(photometry: LdtPhotometry, *, tolerance_pct: float = 1.0) -> dict[str, object]:
    """Return the LDT grid and C-plane mirror-pair diagnostics."""
    photometry.validate()
    angles = photometry.c_angles_deg
    pairs: list[dict[str, object]] = []
    used: set[int] = set()
    for index, angle in enumerate(angles):
        if index in used:
            continue
        mirror = (180.0 - angle) % 360.0
        mirror_index = min(range(len(angles)), key=lambda item: abs(((angles[item] - mirror + 180.0) % 360.0) - 180.0))
        if mirror_index == index:
            used.add(index)
            pairs.append({
                "c_deg": angle,
                "mirror_c_deg": angle,
                "max_difference_pct": 0.0,
                "worst_gamma_deg": 0.0,
                "symmetric": True,
                "self_plane": True,
            })
            continue
        if mirror_index in used:
            used.add(index)
            continue
        used.update((index, mirror_index))
        differences = []
        for left, right in zip(photometry.intensities_cd_per_klm[index], photometry.intensities_cd_per_klm[mirror_index]):
            denominator = max(abs(left), abs(right), 1e-9)
            differences.append(abs(left - right) / denominator * 100.0)
        maximum = max(differences, default=0.0)
        worst_gamma = photometry.gamma_angles_deg[differences.index(maximum)] if differences else 0.0
        pairs.append({
            "c_deg": angle,
            "mirror_c_deg": angles[mirror_index],
            "max_difference_pct": maximum,
            "worst_gamma_deg": worst_gamma,
            "symmetric": maximum <= tolerance_pct,
        })
    return {
        "name": photometry.name,
        "company": photometry.company,
        "flux_lm": photometry.flux_lm,
        "power_w": photometry.power_w,
        "c_angles_deg": photometry.c_angles_deg,
        "gamma_angles_deg": photometry.gamma_angles_deg,
        "intensities_cd_per_klm": photometry.intensities_cd_per_klm,
        "max_intensity_cd_per_klm": max((max(row) for row in photometry.intensities_cd_per_klm), default=0.0),
        "symmetry_tolerance_pct": tolerance_pct,
        "pairs": pairs,
        "symmetric": all(bool(pair["symmetric"]) for pair in pairs),
    }


def parse_ldt(path: str | Path) -> LdtPhotometry:
    data = Path(path).read_bytes()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    return parse_ldt_text(text)


def parse_ldt_text(text: str) -> LdtPhotometry:
    lines = text.splitlines()
    company = _line(lines, 0, "company")
    symmetry = _integer(_line(lines, 2, "symmetry"), "symmetry")
    mc = _integer(_line(lines, 3, "C plane count"), "C plane count")
    dc = _number(_line(lines, 4, "C step"), "C step")
    ng = _integer(_line(lines, 5, "gamma count"), "gamma count")
    dg = _number(_line(lines, 6, "gamma step"), "gamma step")
    if mc <= 0 or ng <= 0:
        raise LdtError("Invalid LDT axes")

    dimensions = tuple(_number(_line(lines, 12 + i, f"dimension {i}"), "dimension") for i in range(3))
    lorl = _number(_line(lines, 22, "LORL"), "LORL")
    conversion = _number(_line(lines, 23, "conversion"), "conversion")
    n_sets = _integer(_line(lines, 25, "lamp set count"), "lamp set count")
    if n_sets <= 0:
        raise LdtError("LDT must contain at least one lamp set")

    base = 26
    lamp_sets: list[LampSet] = []
    for index in range(n_sets):
        offset = base + index * 6
        lamp_sets.append(
            LampSet(
                _line(lines, offset, "number of lamps"),
                _line(lines, offset + 1, "lamp type"),
                _number(_line(lines, offset + 2, "lamp flux"), "lamp flux"),
                _line(lines, offset + 3, "lamp color"),
                _line(lines, offset + 4, "lamp CRI"),
                _number(_line(lines, offset + 5, "lamp wattage"), "lamp wattage"),
            )
        )
    base += n_sets * 6
    base += 10  # DR values
    c_count_in_file = {0: mc, 1: 1, 2: mc // 2 + 1, 3: mc // 2 + 1, 4: mc // 4 + 1}.get(symmetry, mc)
    c_angles_file = [_number(_line(lines, base + i, f"C[{i}]"), "C angle") for i in range(mc)]
    base += mc
    gamma_angles = [_number(_line(lines, base + i, f"gamma[{i}]"), "gamma angle") for i in range(ng)]
    base += ng
    raw_count = c_count_in_file * ng
    raw = [_number(_line(lines, base + i, f"I[{i}]"), "intensity") for i in range(raw_count)]
    c_file = c_angles_file[:c_count_in_file]
    matrix_file = [raw[i * ng:(i + 1) * ng] for i in range(c_count_in_file)]
    matrix = _expand_symmetry(matrix_file, mc, ng, symmetry)
    # A few laboratory exports leave Dc/Dg at zero while writing valid
    # explicit axes. The explicit axes are authoritative in that case.
    if dc <= 0:
        dc = c_angles_file[1] - c_angles_file[0]
    if dg <= 0:
        dg = gamma_angles[1] - gamma_angles[0]
    result = LdtPhotometry(
        company=company,
        name=_line(lines, 8, "luminaire name"),
        c_angles_deg=c_angles_file,
        gamma_angles_deg=gamma_angles,
        intensities_cd_per_klm=matrix,
        lamp_sets=lamp_sets,
        symmetry=0,
        conversion=conversion,
        lorl_percent=lorl,
        dimensions_mm=dimensions,
        metadata={"source_report": _line(lines, 7, "report"), "source_date": _line(lines, 11, "date")},
    )
    result.validate()
    return result


def _expand_symmetry(matrix: list[list[float]], mc: int, ng: int, symmetry: int) -> list[list[float]]:
    if symmetry == 0:
        return [row[:] for row in matrix]
    expanded = [[0.0] * ng for _ in range(mc)]
    if symmetry == 1:
        return [matrix[0][:] for _ in range(mc)]
    if symmetry in (2, 3):
        half = mc // 2
        for c in range(mc):
            source = c if c <= half else mc - c
            expanded[c] = matrix[source][:]
        return expanded
    quarter = mc // 4
    for c in range(mc):
        reduced = c % (2 * quarter)
        source = reduced if reduced <= quarter else 2 * quarter - reduced
        expanded[c] = matrix[source][:]
    return expanded


def write_ldt(photometry: LdtPhotometry, path: str | Path) -> None:
    photometry.validate()
    path = Path(path)
    path.write_text(ldt_text(photometry), encoding="latin-1", newline="\n")


def ldt_text(photometry: LdtPhotometry) -> str:
    photometry.validate()
    c_angles = photometry.c_angles_deg
    gamma_angles = photometry.gamma_angles_deg
    dc = c_angles[1] - c_angles[0]
    dg = gamma_angles[1] - gamma_angles[0]
    # EULUMDAT fields 12..21 are the three dimensions, six mounting
    # dimensions and the downward flux fraction. Keep all 26 header fields so
    # the result can be consumed by standard LDT readers.
    length, width, height = photometry.dimensions_mm
    lines = [
        photometry.company, "1", "0", str(len(c_angles)), f"{dc:.6g}",
        str(len(gamma_angles)), f"{dg:.6g}", photometry.metadata.get("source_report", "SALVI calculated"),
        photometry.name, "", "", photometry.metadata.get("source_date", ""),
        f"{length:.6g}", f"{width:.6g}", f"{height:.6g}",
        f"{length:.6g}", f"{width:.6g}", f"{height:.6g}",
        f"{height:.6g}", f"{height:.6g}", f"{height:.6g}", "100.0",
        f"{photometry.lorl_percent:.6g}", f"{photometry.conversion:.6g}", "0.0", str(len(photometry.lamp_sets)),
    ]
    for lamp in photometry.lamp_sets:
        lines.extend([lamp.number_of_lamps, lamp.lamp_type, f"{lamp.flux_lm:.6g}", lamp.color, lamp.cri, f"{lamp.wattage_w:.6g}"])
    lines.extend(["0.0"] * 10)
    lines.extend(f"{value:.6g}" for value in c_angles)
    lines.extend(f"{value:.6g}" for value in gamma_angles)
    for row in photometry.intensities_cd_per_klm:
        lines.extend(f"{value:.6g}" for value in row)
    return "\n".join(lines) + "\n"
