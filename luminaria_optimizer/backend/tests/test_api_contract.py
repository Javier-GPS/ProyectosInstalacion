from luminaire_optimizer.api import GeometryTraceRequest, GroupRequest, app


def test_api_metadata():
    assert app.title == "SALVI Luminaria Optimizer"
    paths = {route.path for route in app.routes}
    assert "/api/optimize" in paths
    assert "/api/road/calculate" in paths
    assert "/api/ldt/inspect" in paths
    assert "/api/geometry/trace" in paths


def test_api_accepts_optional_complete_luminaire_ldt_reference():
    assert "reference_luminaire_ldt_base64" in GroupRequest.model_fields
    assert GroupRequest.model_fields["reference_luminaire_ldt_base64"].default is None


def test_geometry_trace_defaults_to_previewable_pmma_trace():
    assert GeometryTraceRequest.model_fields["sample_count"].default == 10_000
    assert GeometryTraceRequest.model_fields["lens_index"].default == 1.49
    assert GeometryTraceRequest.model_fields["rayset_base64"].default is None


def test_geometry_trace_exposes_bounded_visual_preview_contract():
    assert GeometryTraceRequest.model_fields["preview_ray_count"].default == 5_000
    assert GeometryTraceRequest.model_fields["preview_ray_count"].metadata[1].le == 20_000
    assert GeometryTraceRequest.model_fields["c_mirror"].default is True
    assert GeometryTraceRequest.model_fields["c_offset_deg"].default == 0.0
