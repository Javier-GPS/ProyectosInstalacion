"""EULUMDAT (LDT) parser.

LDT files are commonly exported as either Latin-1 or UTF-8.  The parser is a
shared ingestion boundary for uploads and catalog files, so failures should be
reported as malformed input rather than leaking ``IndexError``/``ValueError``
from a particular line.
"""
from pathlib import Path


class LdtParseError(ValueError):
    """Raised when an LDT file cannot be decoded or does not match its format."""


def _decode_ldt(data: bytes) -> str:
    """Decode the two encodings emitted by the LDT files we accept."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _line(lines: list[str], index: int, field: str) -> str:
    if index >= len(lines):
        raise LdtParseError(
            f"Missing {field} at line {index + 1}; expected at least {index + 1} lines"
        )
    return lines[index].strip()


def _int(lines: list[str], index: int, field: str) -> int:
    value = _line(lines, index, field)
    try:
        return int(value)
    except ValueError as exc:
        raise LdtParseError(f"Invalid integer for {field} at line {index + 1}: {value!r}") from exc


def _float(lines: list[str], index: int, field: str) -> float:
    value = _line(lines, index, field).replace(",", ".")
    try:
        return float(value)
    except ValueError as exc:
        raise LdtParseError(f"Invalid number for {field} at line {index + 1}: {value!r}") from exc


def parse_ldt(path):
    path = Path(path)
    text = _decode_ldt(path.read_bytes())
    lines = text.splitlines()
    L = lines
    d = {}
    d["company"] = _line(L, 0, "company")
    d["Ityp"] = _int(L, 1, "Ityp")
    d["Isym"] = _int(L, 2, "Isym")
    d["Mc"] = _int(L, 3, "Mc")
    d["Dc"] = _float(L, 4, "Dc")
    d["Ng"] = _int(L, 5, "Ng")
    d["Dg"] = _float(L, 6, "Dg")
    d["report"] = _line(L, 7, "report")
    d["lum_name"] = _line(L, 8, "lum_name")
    d["lum_num"] = _line(L, 9, "lum_num")
    d["filename"] = _line(L, 10, "filename")
    d["date_user"] = _line(L, 11, "date_user")
    d["length_mm"] = _float(L, 12, "length_mm")
    d["width_mm"] = _float(L, 13, "width_mm")
    d["height_mm"] = _float(L, 14, "height_mm")
    d["la_length"] = _float(L, 15, "la_length")
    d["la_width"] = _float(L, 16, "la_width")
    d["la_h_C0"] = _float(L, 17, "la_h_C0")
    d["la_h_C90"] = _float(L, 18, "la_h_C90")
    d["la_h_C180"] = _float(L, 19, "la_h_C180")
    d["la_h_C270"] = _float(L, 20, "la_h_C270")
    d["DFF"] = _float(L, 21, "DFF")
    d["LORL"] = _float(L, 22, "LORL")
    d["conv"] = _float(L, 23, "conv")
    d["tilt"] = _float(L, 24, "tilt")
    d["n_sets"] = _int(L, 25, "n_sets")
    if d["Mc"] <= 0 or d["Ng"] <= 0 or d["n_sets"] <= 0:
        raise LdtParseError("Mc, Ng and n_sets must be positive")
    base = 26
    sets = []
    for s in range(d["n_sets"]):
        b = base + s * 6
        sets.append(
            {
                "n_lamps": _line(L, b, f"lamp set {s + 1} n_lamps"),
                "lamp_type": _line(L, b + 1, f"lamp set {s + 1} lamp_type"),
                "flux_lm": _float(L, b + 2, f"lamp set {s + 1} flux_lm"),
                "color": _line(L, b + 3, f"lamp set {s + 1} color"),
                "CRI": _line(L, b + 4, f"lamp set {s + 1} CRI"),
                "wattage": _float(L, b + 5, f"lamp set {s + 1} wattage"),
            }
        )
    d["lamp_sets"] = sets
    base = base + d["n_sets"] * 6
    d["DR"] = [_float(L, base + i, f"DR[{i}]") for i in range(10)]
    base += 10
    d["C"] = [_float(L, base + i, f"C[{i}]") for i in range(d["Mc"])]
    base += d["Mc"]
    d["G"] = [_float(L, base + i, f"G[{i}]") for i in range(d["Ng"])]
    base += d["Ng"]
    if d["Isym"] == 0:
        n_planes = d["Mc"]
    elif d["Isym"] == 1:
        n_planes = 1
    elif d["Isym"] == 2:
        n_planes = d["Mc"] // 2 + 1
    elif d["Isym"] == 3:
        n_planes = d["Mc"] // 2 + 1
    elif d["Isym"] == 4:
        n_planes = d["Mc"] // 4 + 1
    else:
        n_planes = d["Mc"]
    d["n_planes_in_file"] = n_planes
    n_int = n_planes * d["Ng"]
    I_raw = [_float(L, base + i, f"I[{i}]") for i in range(n_int)]
    d["I_raw"] = I_raw
    full_I = [[0.0] * d["Ng"] for _ in range(d["Mc"])]
    if d["Isym"] == 0:
        for c in range(d["Mc"]):
            for g in range(d["Ng"]):
                full_I[c][g] = I_raw[c * d["Ng"] + g]
    elif d["Isym"] == 1:
        for c in range(d["Mc"]):
            for g in range(d["Ng"]):
                full_I[c][g] = I_raw[g]
    elif d["Isym"] in (2, 3):
        half = d["Mc"] // 2
        for c in range(d["Mc"]):
            cf = c if c <= half else (d["Mc"] - c)
            for g in range(d["Ng"]):
                full_I[c][g] = I_raw[cf * d["Ng"] + g]
    elif d["Isym"] == 4:
        q = d["Mc"] // 4
        for c in range(d["Mc"]):
            r = c % (2 * q)
            cf = r if r <= q else (2 * q - r)
            for g in range(d["Ng"]):
                full_I[c][g] = I_raw[cf * d["Ng"] + g]
    d["I"] = full_I
    return d


if __name__ == "__main__":
    import sys
    import glob

    pattern = sys.argv[1] if len(sys.argv) > 1 else "*.ldt"
    for f in sorted(glob.glob(pattern)):
        d = parse_ldt(f)
        s = d["lamp_sets"][0]
        print(
            f"{Path(f).name}: {d['lum_name']} | "
            f"Isym={d['Isym']} Mc={d['Mc']} Ng={d['Ng']} | "
            f"{s['flux_lm']:.0f} lm {s['wattage']:.0f} W "
            f"({s['flux_lm']/s['wattage']:.1f} lm/W)"
        )
