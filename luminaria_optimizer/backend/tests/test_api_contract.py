from luminaire_optimizer.api import app


def test_api_metadata():
    assert app.title == "SALVI Luminaria Optimizer"
    paths = {route.path for route in app.routes}
    assert "/api/optimize" in paths
    assert "/api/road/calculate" in paths
    assert "/api/ldt/inspect" in paths
