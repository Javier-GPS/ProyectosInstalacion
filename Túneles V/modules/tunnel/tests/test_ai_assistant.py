import pytest

from modules.tunnel.ai_assistant import build_context, _normalise_report


def test_build_context_keeps_calculation_evidence_and_bounds_profile():
    form = {
        "project_name": "Túnel de prueba",
        "length_m": 1000,
        "lum_config": {"I_max_mA": 700, "U0_obj": 0.4},
        "manual_luminaire_overrides": {"Umbral A|12": {"values": {"current_mA": 500}}},
    }
    result = {
        "summary": {"Lth": 92, "Lin": 2.5},
        "zones": {"threshold": {"zone_name": "Umbral A", "L_required": 92}},
    }
    form["photometric_result"] = {
        "real_profile": {"fields": [{"s": index} for index in range(700)]}
    }
    context = build_context(form, result)

    assert context["inputs"]["length_m"] == 1000
    assert context["calculated"]["summary"]["Lth"] == 92
    assert len(context["photometric"]["profile_fields"]) == 500
    assert context["manual_overrides"]["luminaire"]["Umbral A|12"]["values"]["current_mA"] == 500


def test_normalise_report_discards_malformed_items_and_bounds_text():
    report = _normalise_report({
        "answer": "ok",
        "findings": [{"severity": "not-valid", "title": "x"}, "invalid"],
        "suggestions": [{"title": "s", "changes": [
            {"path": "lum_config.I_max_mA", "value": 700, "unit": "mA"},
            {"path": "bad", "value": {"not": "scalar"}},
        ]}],
        "normative_references": [{"standard": "CIE 140:2019"}],
        "limitations": ["limit"],
    })

    assert report["findings"][0]["severity"] == "info"
    assert len(report["findings"]) == 1
    assert report["suggestions"][0]["changes"] == [{
        "path": "lum_config.I_max_mA",
        "value": 700,
        "unit": "mA",
        "scope": "",
    }]
    assert report["needs_calculation"] is True


def test_ai_module_does_not_require_anthropic_until_ask(monkeypatch):
    from modules.tunnel import ai_assistant

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        ai_assistant.ask("¿Qué está fallando?", {})
