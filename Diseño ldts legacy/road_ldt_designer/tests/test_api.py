from road_ldt_designer.api import _build_request, app


def test_api_lists_m_lighting_classes():
    client = app.test_client()

    response = client.get("/api/lighting-classes")

    assert response.status_code == 200
    assert [item["code"] for item in response.get_json()] == [
        "M1",
        "M2",
        "M3",
        "M4",
        "M5",
        "M6",
    ]


def test_api_builds_custom_quality_targets():
    optimization_request, options = _build_request(
        {
            "geometry": {"lane_widths_m": [3.5, 3.5]},
            "installation": {"arrangement_type": "unilateral"},
            "requirements": {
                "lighting_class": "CUSTOM",
                "include_rei": True,
                "custom_targets": {
                    "luminance_avg_min_cd_m2": 1.1,
                    "uo_min": 0.46,
                    "ul_min": 0.68,
                    "ti_max_pct": 12.0,
                    "rei_min": 0.34,
                },
            },
        }
    )

    assert optimization_request.targets.luminance_avg_min_cd_m2 == 1.1
    assert optimization_request.targets.uo_min == 0.46
    assert optimization_request.targets.ul_min == 0.68
    assert optimization_request.targets.ti_max_pct == 12.0
    assert optimization_request.targets.rei_min == 0.34
    assert options.evaluate_edge_metrics is True


def test_api_runs_small_optimization_without_intrusion():
    client = app.test_client()
    response = client.post(
        "/api/optimize",
        json={
            "project_name": "API test",
            "geometry": {
                "lane_widths_m": [3.5, 3.5],
                "calculation_length_m": 20,
                "longitudinal_points": 2,
                "transverse_points_per_lane": 1,
            },
            "installation": {
                "arrangement_type": "unilateral",
                "spacing_m": 20,
                "mounting_height_m": 8,
                "flux_lm": 10000,
                "pole_setback_m": 1,
                "overhang_m": 1,
            },
            "requirements": {
                "lighting_class": "M6",
                "include_rei": False,
                "evaluate_intrusion": False,
            },
            "optimizer": {"max_candidates": 3},
        },
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["status"] == "complete"
    assert payload["optimizer"]["evaluated_candidates"] == 3
    assert payload["metrics"]["intrusion_max_lx"] is None
    assert payload["ldt_text"].startswith("SALVI\n")
    assert payload["photometry"]["source"] == "round_trip_ldt"
    assert payload["photometry"]["c_step_deg"] == 1.0
    assert payload["photometry"]["gamma_step_deg"] == 1.0
    assert payload["photometry"]["peak_intensity_cd_per_klm"] > 0
    assert 0 <= payload["photometry"]["peak_gamma_deg"] <= 90
    assert payload["photometry"]["gamma_width_90_deg"] >= 0
    assert (
        payload["photometry"]["gamma_fwhm_deg"]
        >= payload["photometry"]["gamma_width_90_deg"]
    )
    assert len(payload["photometry"]["c_angles_deg"]) == 360
    assert len(payload["photometry"]["gamma_angles_deg"]) == 181
    ldt_lines = payload["ldt_text"].splitlines()
    assert ldt_lines[25] == "1"  # standard L26 lamp-set count


def test_api_validates_physical_ldt_against_target_on_same_street():
    client = app.test_client()
    project = {
        "project_name": "API physical validation",
        "geometry": {
            "lane_widths_m": [3.5, 3.5],
            "calculation_length_m": 20,
            "longitudinal_points": 2,
            "transverse_points_per_lane": 1,
        },
        "installation": {
            "arrangement_type": "unilateral",
            "spacing_m": 20,
            "mounting_height_m": 8,
            "flux_lm": 10000,
            "pole_setback_m": 1,
            "overhang_m": 1,
        },
        "requirements": {
            "lighting_class": "M6",
            "include_rei": False,
            "evaluate_intrusion": False,
        },
        "optimizer": {"max_candidates": 3},
    }
    optimized = client.post("/api/optimize", json=project).get_json()
    validation = client.post(
        "/api/validate-ldt",
        json={
            **project,
            "physical_filename": "same-as-target.ldt",
            "physical_ldt_text": optimized["ldt_text"],
            "target_ldt_text": optimized["ldt_text"],
            "correction_gain": 0.65,
        },
    )

    payload = validation.get_json()
    assert validation.status_code == 200
    assert payload["status"] == "complete"
    assert payload["filename"] == "same-as-target.ldt"
    assert payload["comparison"]["normalized_rmse_pct"] == 0.0
    assert payload["comparison"]["shape_correlation"] == 1.0
    assert payload["metric_deltas"]["uo"] == 0.0
    assert payload["photometry"]["source"] == "physical_ldt"
    assert payload["residual_map"]["minimum_error_pct"] == 0.0
    assert payload["residual_map"]["maximum_error_pct"] == 0.0
    assert payload["compensation"]["correction_gain"] == 0.65
    assert payload["compensation"]["pre_distortion_rmse_pct"] == 0.0
    assert payload["compensation"]["photometry"]["source"] == "compensated_target"
    assert payload["compensation"]["ldt_text"].startswith("SALVI\n")
