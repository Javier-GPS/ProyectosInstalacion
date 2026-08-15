from luminaire_optimizer.api import GroupRequest, app


def test_api_metadata():
    assert app.title == "SALVI Luminaria Optimizer"
    paths = {route.path for route in app.routes}
    assert "/api/optimize" in paths
    assert "/api/road/calculate" in paths
    assert "/api/ldt/inspect" in paths


def test_api_accepts_optional_complete_luminaire_ldt_reference():
    assert "reference_luminaire_ldt_base64" in GroupRequest.model_fields
    assert GroupRequest.model_fields["reference_luminaire_ldt_base64"].default is None
