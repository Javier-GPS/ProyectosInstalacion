"""Reduced-luminance table loader for R1-R4 and custom C2 files."""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ReducedLuminanceTable:
    name: str
    tan_gamma: tuple[float, ...]
    beta_deg: tuple[float, ...]
    values_r_times_10000: tuple[tuple[float, ...], ...]
    source: str = ""
    q0: float | None = None

    def __post_init__(self) -> None:
        if len(self.values_r_times_10000) != len(self.tan_gamma):
            raise ValueError("r-table row count does not match tan-gamma axis")
        if any(len(row) != len(self.beta_deg) for row in self.values_r_times_10000):
            raise ValueError("r-table column count does not match beta axis")
        if any(b <= a for a, b in zip(self.tan_gamma, self.tan_gamma[1:])) or any(b <= a for a, b in zip(self.beta_deg, self.beta_deg[1:])):
            raise ValueError("r-table axes must be strictly increasing")

    def value(self, tan_gamma: float, beta_deg: float) -> float:
        tg = max(self.tan_gamma[0], min(self.tan_gamma[-1], float(tan_gamma)))
        beta = abs(float(beta_deg)) % 360.0
        beta = 360.0 - beta if beta > 180.0 else beta
        ti = max(0, min(len(self.tan_gamma) - 2, bisect.bisect_right(self.tan_gamma, tg) - 1))
        bi = max(0, min(len(self.beta_deg) - 2, bisect.bisect_right(self.beta_deg, beta) - 1))
        t0, t1 = self.tan_gamma[ti], self.tan_gamma[ti + 1]
        b0, b1 = self.beta_deg[bi], self.beta_deg[bi + 1]
        v00, v01 = self.values_r_times_10000[ti][bi:bi + 2]
        v10, v11 = self.values_r_times_10000[ti + 1][bi:bi + 2]
        wt = (tg - t0) / (t1 - t0) if t1 != t0 else 0.0
        wb = (beta - b0) / (b1 - b0) if b1 != b0 else 0.0
        if 0 in (v00, v01, v10, v11):
            return 0.0
        return ((1 - wt) * ((1 - wb) * v00 + wb * v01) + wt * ((1 - wb) * v10 + wb * v11)) / 10000.0


def load_rtable(path: str | Path, *, name: str | None = None) -> ReducedLuminanceTable:
    lines = [line.strip().replace(",", ".") for line in Path(path).read_text(encoding="latin-1").splitlines() if line.strip()]
    if not lines or lines[0].lower() != "rtable.v1":
        raise ValueError("unsupported r-table header")
    cursor = 1
    table_name = lines[cursor]; cursor += 1
    declared_row_count = int(lines[cursor]); cursor += 1
    expected_beta = (0.0, 2.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 60.0, 75.0, 90.0, 105.0, 120.0, 135.0, 150.0, 165.0, 180.0)
    marker = None
    # Locate the beta-count marker by its complete canonical axis. This also
    # accepts C2 Extended 20 files whose declared row count is still 29.
    for index in range(cursor, len(lines) - len(expected_beta) - 1):
        if int(float(lines[index])) != len(expected_beta):
            continue
        candidate = tuple(float(lines[index + 1 + offset]) for offset in range(len(expected_beta)))
        if candidate == expected_beta:
            marker = index
            break
    if marker is None:
        row_count = declared_row_count
        tan_axis = tuple(float(lines[cursor + i]) for i in range(row_count))
        cursor += row_count
        col_count = int(lines[cursor]); cursor += 1
        beta_axis = tuple(float(lines[cursor + i]) for i in range(col_count)); cursor += col_count
    else:
        tan_axis = tuple(float(value) for value in lines[cursor:marker])
        row_count = len(tan_axis)
        if row_count < 2:
            raise ValueError("r-table has fewer than two tan-gamma rows")
        cursor = marker
        col_count = int(lines[cursor]); cursor += 1
        beta_axis = tuple(float(lines[cursor + i]) for i in range(col_count)); cursor += col_count
    expected = row_count * col_count
    remaining = len(lines) - cursor
    q0 = None
    if remaining == expected + 1:
        q0 = float(lines[cursor])
        cursor += 1
    if len(lines) - cursor < expected:
        raise ValueError(
            f"r-table data is incomplete: found {row_count} rows x {col_count} columns"
        )
    values: list[tuple[float, ...]] = []
    for row in range(row_count):
        values.append(tuple(float(lines[cursor + row * col_count + col]) for col in range(col_count)))
    return ReducedLuminanceTable(name or table_name, tan_axis, beta_axis, tuple(values), str(path), q0)
