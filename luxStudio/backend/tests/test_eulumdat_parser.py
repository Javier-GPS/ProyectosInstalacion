from pathlib import Path

import pytest

from app.salvi_lighting import LdtParseError, parse_ldt


def _minimal_ldt() -> str:
    lines = [
        "Salvi Café",
        "1", "1", "4", "90", "3", "90",
        "report", "Luminaria de prueba", "1", "test.ldt", "2026",
        "100,0", "80", "50", "90", "40", "10", "10", "10", "10",
        "0", "95,5", "1", "0", "1",
        "1", "LED", "1000,5", "4000K", "80", "10,5",
        *("1" for _ in range(10)),
        "0", "90", "180", "270",
        "0", "90", "180",
        "10", "20", "30",
    ]
    return "\r\n".join(lines) + "\r\n"


@pytest.mark.parametrize("encoding", ["utf-8", "latin-1"])
def test_parse_ldt_accepts_common_encodings_and_decimal_commas(tmp_path: Path, encoding: str):
    path = tmp_path / "sample.ldt"
    path.write_bytes(_minimal_ldt().encode(encoding))

    parsed = parse_ldt(path)

    assert parsed["company"] == "Salvi Café"
    assert parsed["length_mm"] == 100.0
    assert parsed["LORL"] == 95.5
    assert parsed["lamp_sets"][0]["flux_lm"] == 1000.5
    assert parsed["lamp_sets"][0]["wattage"] == 10.5
    assert parsed["I"] == [[10.0, 20.0, 30.0]] * 4


def test_parse_ldt_reports_the_missing_line(tmp_path: Path):
    path = tmp_path / "broken.ldt"
    path.write_text("Salvi\n1\n", encoding="utf-8")

    with pytest.raises(LdtParseError, match=r"Missing Isym at line 3"):
        parse_ldt(path)


def test_parse_ldt_reports_invalid_numeric_field(tmp_path: Path):
    lines = _minimal_ldt().splitlines()
    lines[22] = "not-a-number"
    path = tmp_path / "broken-number.ldt"
    path.write_text("\n".join(lines), encoding="utf-8")

    with pytest.raises(LdtParseError, match=r"Invalid number for LORL at line 23"):
        parse_ldt(path)
