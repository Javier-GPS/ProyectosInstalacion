from zipfile import ZipFile

from luminaire_optimizer.api import CadOpenRequest, GeometryTraceRequest, GroupRequest, _extract_cad_archive, _history_path, app


def test_api_metadata():
    assert app.title == "SALVI Luminaria Optimizer"
    paths = {route.path for route in app.routes}
    assert "/api/optimize" in paths
    assert "/api/road/calculate" in paths
    assert "/api/ldt/inspect" in paths
    assert "/api/geometry/trace" in paths
    assert "/api/default-resources" in paths


def test_api_accepts_optional_complete_luminaire_ldt_reference():
    assert "reference_luminaire_ldt_base64" in GroupRequest.model_fields
    assert GroupRequest.model_fields["reference_luminaire_ldt_base64"].default is None


def test_api_accepts_native_cad_modes_and_archives(tmp_path):
    assert set(CadOpenRequest.model_fields) == {"cad_base64", "cad_filename"}
    archive_path = tmp_path / "modelo.zip"
    extract_path = tmp_path / "extracted"
    extract_path.mkdir()
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("modelo/ensamblaje.SLDASM", b"assembly")
        archive.writestr("modelo/lente.SLDPRT", b"part")
    _extract_cad_archive(archive_path, extract_path, ".zip")
    assert (extract_path / "modelo" / "ensamblaje.SLDASM").is_file()
    assert (extract_path / "modelo" / "lente.SLDPRT").is_file()


def test_geometry_trace_defaults_to_previewable_pmma_trace():
    assert GeometryTraceRequest.model_fields["sample_count"].default == 10_000
    assert GeometryTraceRequest.model_fields["lens_index"].default == 1.49
    assert GeometryTraceRequest.model_fields["rayset_base64"].default is None


def test_geometry_trace_exposes_bounded_visual_preview_contract():
    assert GeometryTraceRequest.model_fields["preview_ray_count"].default == 5_000
    assert GeometryTraceRequest.model_fields["preview_ray_count"].metadata[1].le == 20_000
    assert GeometryTraceRequest.model_fields["c_mirror"].default is True
    assert GeometryTraceRequest.model_fields["c_offset_deg"].default == 0.0


def test_cad_history_paths_never_overwrite_a_previous_candidate(tmp_path):
    first = _history_path(tmp_path, "lente", ".SLDPRT")
    first.touch()
    second = _history_path(tmp_path, "lente", ".SLDPRT")

    assert first != second
    assert second.name.startswith("lente_candidate_")
