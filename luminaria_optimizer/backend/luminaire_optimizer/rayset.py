"""Reader for binary IES TM-25-13 ray sets.

The ray payload is exposed as a read-only NumPy memmap so large vendor ray
files can be sampled or processed in chunks without duplicating them in RAM.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np


class Tm25Error(ValueError):
    """Raised when a TM-25 ray file is malformed or unsupported."""


@dataclass(frozen=True)
class Tm25SpectralTable:
    """One optional TM-25 spectral table."""

    wavelengths_nm: tuple[float, ...]
    weights: tuple[float, ...]


@dataclass(frozen=True)
class Tm25Header:
    """Metadata parsed from the TM-25 header blocks."""

    version: int
    creation_method: int
    luminous_flux_lm: float
    radiant_flux: float
    ray_count: int
    creation_datetime: str
    start_position: int
    spectrum_type: int
    wavelength_nm: float
    wavelength_min_nm: float
    wavelength_max_nm: float
    spectral_tables: tuple[Tm25SpectralTable, ...]
    additional_text: str
    descriptions: dict[str, str]
    flags: dict[str, bool]


_FIXED_HEADER_BYTES = 256
_FLAGS_OFFSET = 256
_FLAGS_BYTES = 32
_DESCRIPTION_OFFSET = _FLAGS_OFFSET + _FLAGS_BYTES
_DESCRIPTION_BLOCK_BYTES = 9 * 4000
_DATA_OFFSET = _DESCRIPTION_OFFSET + _DESCRIPTION_BLOCK_BYTES
_STANDARD_DESCRIPTIONS = (
    "name",
    "manufacturer",
    "model_creator",
    "rayfile_creator",
    "equipment",
    "camera",
    "lightsource",
    "additional_info",
    "data_reference",
)


def _read_exact(handle, size: int, label: str) -> bytes:
    data = handle.read(size)
    if len(data) != size:
        raise Tm25Error(f"truncated {label}: expected {size} bytes, got {len(data)}")
    return data


def _u32_text(data: bytes) -> str:
    try:
        return data.decode("utf-32-le").split("\x00", 1)[0]
    except UnicodeDecodeError as exc:
        raise Tm25Error("invalid UTF-32 text block") from exc


def _items_from_flags(flags: dict[str, bool], additional: list[str]) -> tuple[str, ...]:
    items = ["x", "y", "z", "kx", "ky", "kz"]
    if flags["radiant_flux"]:
        items.append("phi")
    if flags["wavelength"]:
        items.append("lambda")
    if flags["luminous_flux"]:
        items.append("Tri_Y")
    if flags["stokes"]:
        items.extend(("S1", "S2", "S3", "PolEllipseX", "PolEllipseY", "PolEllipseZ"))
    if flags["tristimulus"]:
        items.extend(("Tri_X", "Tri_Z"))
    if flags["spectrum_index"]:
        items.append("spectrumIdx")
    items.extend(additional)
    return tuple(items)


def parse_tm25(path: str | Path, *, mode: str = "r") -> "Tm25RaySet":
    """Parse a TM-25 file and memory-map its ray records.

    The parser validates the complete file length before creating the memmap.
    ``mode`` is normally ``"r"``; writable modes are accepted for controlled
    preprocessing but are not needed by the optical simulation.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise Tm25Error(f"ray file does not exist: {file_path}")

    with file_path.open("rb") as handle:
        fixed = _read_exact(handle, _FIXED_HEADER_BYTES, "file header")
        if fixed[:4] != b"TM25":
            raise Tm25Error(f"invalid TM-25 magic: {fixed[:4]!r}")

        version, creation_method = struct.unpack_from("<ii", fixed, 4)
        if version != 2013:
            raise Tm25Error(f"unsupported TM-25 version: {version}")
        luminous_flux, radiant_flux = struct.unpack_from("<ff", fixed, 12)
        ray_count = struct.unpack_from("<Q", fixed, 20)[0]
        creation_datetime = fixed[28:56].split(b"\x00", 1)[0].decode("ascii", "replace")
        start_position, spectrum_type = struct.unpack_from("<ii", fixed, 56)
        wavelength_nm, wavelength_min_nm, wavelength_max_nm = struct.unpack_from("<fff", fixed, 64)
        n_spectra, n_additional, additional_text_bytes = struct.unpack_from("<iii", fixed, 76)
        if ray_count <= 0:
            raise Tm25Error("TM-25 file contains no rays")
        if n_spectra < 0 or n_additional < 0 or additional_text_bytes < 0:
            raise Tm25Error("TM-25 header contains a negative block size")
        if additional_text_bytes % 32:
            raise Tm25Error("TM-25 additional text size must be a multiple of 32")

        flags_raw = struct.unpack("<8i", _read_exact(handle, _FLAGS_BYTES, "known flags block"))
        (
            position_flag,
            direction_flag,
            radiant_flag,
            wavelength_flag,
            luminous_flag,
            stokes_flag,
            tristimulus_flag,
            spectrum_index_flag,
        ) = flags_raw
        if position_flag != 1 or direction_flag != 1:
            raise Tm25Error("TM-25 position and direction flags must both be 1")
        if radiant_flag not in (0, 1) or wavelength_flag not in (0, 1):
            raise Tm25Error("TM-25 flux and wavelength flags must be 0 or 1")
        if luminous_flag not in (0, 1) or stokes_flag not in (0, 1):
            raise Tm25Error("TM-25 luminous and Stokes flags must be 0 or 1")
        if tristimulus_flag not in (0, 1) or spectrum_index_flag not in (0, 1):
            raise Tm25Error("TM-25 tristimulus and spectrum flags must be 0 or 1")
        if not radiant_flag and not luminous_flag:
            raise Tm25Error("TM-25 file has neither radiant nor luminous flux")

        descriptions = {
            name: _u32_text(_read_exact(handle, 4000, f"description {name}"))
            for name in _STANDARD_DESCRIPTIONS
        }

        spectral_tables: list[Tm25SpectralTable] = []
        spectral_block_bytes = 0
        for index in range(n_spectra):
            count = struct.unpack("<i", _read_exact(handle, 4, f"spectral table {index + 1} count"))[0]
            if count <= 0:
                raise Tm25Error(f"spectral table {index + 1} contains no samples")
            pairs = struct.unpack(
                f"<{count * 2}f",
                _read_exact(handle, count * 8, f"spectral table {index + 1}"),
            )
            spectral_tables.append(
                Tm25SpectralTable(
                    wavelengths_nm=tuple(pairs[0::2]),
                    weights=tuple(pairs[1::2]),
                ),
            )
            spectral_block_bytes += 4 + count * 8
        padding = (-spectral_block_bytes) % 32
        if padding:
            _read_exact(handle, padding, "spectral block padding")

        additional_names = [
            _u32_text(_read_exact(handle, 512, f"additional column {index + 1}"))
            for index in range(n_additional)
        ]
        if any(not name for name in additional_names):
            raise Tm25Error("TM-25 additional column names cannot be empty")
        additional_text = _u32_text(
            _read_exact(handle, additional_text_bytes, "additional text")
        ) if additional_text_bytes else ""
        data_offset = handle.tell()

    flags = {
        "radiant_flux": bool(radiant_flag),
        "wavelength": bool(wavelength_flag),
        "luminous_flux": bool(luminous_flag),
        "stokes": bool(stokes_flag),
        "tristimulus": bool(tristimulus_flag),
        "spectrum_index": bool(spectrum_index_flag),
    }
    item_names = _items_from_flags(flags, additional_names)
    expected_size = data_offset + ray_count * len(item_names) * 4
    actual_size = file_path.stat().st_size
    if actual_size != expected_size:
        raise Tm25Error(
            f"ray payload size mismatch: expected file size {expected_size}, got {actual_size}"
        )

    try:
        rays = np.memmap(
            file_path,
            dtype="<f4",
            mode=mode,
            offset=data_offset,
            shape=(ray_count, len(item_names)),
        )
    except (OSError, ValueError) as exc:
        raise Tm25Error(f"cannot map ray payload: {file_path}") from exc

    header = Tm25Header(
        version=version,
        creation_method=creation_method,
        luminous_flux_lm=luminous_flux,
        radiant_flux=radiant_flux,
        ray_count=ray_count,
        creation_datetime=creation_datetime,
        start_position=start_position,
        spectrum_type=spectrum_type,
        wavelength_nm=wavelength_nm,
        wavelength_min_nm=wavelength_min_nm,
        wavelength_max_nm=wavelength_max_nm,
        spectral_tables=tuple(spectral_tables),
        additional_text=additional_text,
        descriptions=descriptions,
        flags=flags,
    )
    return Tm25RaySet(file_path, header, item_names, data_offset, rays)


@dataclass
class Tm25RaySet:
    """Memory-mapped TM-25 ray payload and its column metadata."""

    path: Path
    header: Tm25Header
    item_names: tuple[str, ...]
    data_offset: int
    rays: np.memmap

    @property
    def ray_count(self) -> int:
        return self.header.ray_count

    @property
    def item_count(self) -> int:
        return len(self.item_names)

    @property
    def flux_column(self) -> int:
        """Return the luminous or radiant flux column used by this source."""
        for name in ("phi", "Tri_Y"):
            if name in self.item_names:
                return self.item_names.index(name)
        raise Tm25Error("ray set has no usable flux column")

    def iter_chunks(self, chunk_size: int = 100_000) -> Iterator[np.ndarray]:
        """Yield read-only views of consecutive ray chunks."""
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        for start in range(0, self.ray_count, chunk_size):
            yield self.rays[start:min(start + chunk_size, self.ray_count)]

    def sample(self, count: int, *, seed: int = 0) -> np.ndarray:
        """Return a reproducible copy of ``count`` uniformly sampled rays."""
        if count < 0 or count > self.ray_count:
            raise ValueError("sample count must be between zero and ray_count")
        generator = np.random.default_rng(seed)
        indices = generator.choice(self.ray_count, size=count, replace=False)
        return np.array(self.rays[indices], copy=True)

    def close(self) -> None:
        """Release the underlying memory map, including on Windows."""
        mapped_file = getattr(self.rays, "_mmap", None)
        if mapped_file is not None and not getattr(mapped_file, "closed", False):
            mapped_file.close()
