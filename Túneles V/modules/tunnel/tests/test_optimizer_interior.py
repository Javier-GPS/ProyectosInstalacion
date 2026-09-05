from modules.tunnel.optimizer import _y_positions, optimize_interior
from modules.tunnel.luminaires import (
    TunnelLuminaireResult,
    ZoneLuminaireDesign,
    _y_positions_for_validation,
)
from modules.tunnel.influence_optimizer import _default_y_positions
from modules.tunnel.photometric_verify import compute_real_luminance_profile


def test_central_offset_uses_editable_wall_axis_position():
    assert _y_positions("central_offset", 12.5, 5.25) == [5.25]
    assert _default_y_positions("central_offset", 12.5, 5.25) == [5.25]
    assert _y_positions_for_validation(
        "central_offset", 12.5, 5.25,
    ) == [5.25]


def test_central_double_uses_editable_symmetric_axis_distance():
    assert _y_positions("central_double", 12.5, 5.25) == [5.25, 7.25]
    assert _default_y_positions("central_double", 12.5, 5.25) == [5.25, 7.25]
    assert _y_positions_for_validation(
        "central_double", 12.5, 5.25,
    ) == [5.25, 7.25]


def test_interior_trace_evaluates_all_optics_before_selecting_f151():
    """F2MD/F2M2 deben quedar comprobadas aunque F151 sea la elegida."""
    result = optimize_interior(
        h=4.5,
        w=9.0,
        L_int=3.0,
        U0_obj=0.40,
        Ul_obj=0.60,
        I_max_mA=500.0,
        cct="4000K",
        rtable="R3",
        mf=0.70,
        arrangement="bilateral_sym",
        I_min_pct=0.30,
        tilt_grid=[0.0, 5.0, 10.0, 15.0, 20.0],
        d_min=1.0,
        wall_offset=0.30,
        optimization_goal="min_luminaires",
        spacing_quantum_m=0.5,
    )

    summary = {item["optic"]: item for item in result["candidate_summary"]}
    assert set(summary) == {"F151", "F2MD", "F2M2"}
    assert all(summary[optic]["evaluated"] > 0 for optic in summary)
    assert all(summary[optic]["feasible"] > 0 for optic in summary)
    assert result["optic"] == "F151"
    assert result["d_opt"] == summary["F151"]["max_feasible_spacing_m"]
    assert result["tilt_deg"] == summary["F151"]["best_at_max_spacing"]["tilt_deg"]
    assert result["mA"] == summary["F151"]["best_at_max_spacing"]["current_mA"]
    assert (
        summary["F151"]["max_feasible_spacing_m"]
        >= summary["F2MD"]["max_feasible_spacing_m"]
    )
    assert any(
        row["optic"] == "F2MD" and row["feasible"]
        for row in result["candidate_trace"]
    )


def test_profile_does_not_reuse_portal_reinforcement_field_in_base():
    """La caché periódica de BASE no puede propagar un refuerzo de portal."""
    def make_zone(name, layer, start, end, positions, flux):
        setpoints = [
            {
                "idx": index + 1,
                "s": float(position),
                "optic": "F151",
                "tilt_deg": 10.0,
                "flux_lm": float(flux),
                "spacing_m": 20.0,
                "L_req": 3.0,
            }
            for index, position in enumerate(positions)
        ]
        return ZoneLuminaireDesign(
            zone_type=name, zone_name=name,
            s_start=float(start), s_end=float(end),
            zone_length=float(end - start), L_required=3.0,
            E_required=35.3, model="APHEX_S_75W", pcb="S",
            current_mA=300, flux_lm=float(flux), power_w=60.0,
            optic="F151", d_max_ul=20.0, d_used=20.0,
            n_luminaires=len(setpoints), L_estimated=3.0,
            UF=0.5, power_zone_w=len(setpoints) * 60.0,
            flux_zone_lm=len(setpoints) * float(flux),
            power_density_wm2=0.2, setpoints=setpoints,
            tilt_deg=10.0, Ul=0.61, control_layer=layer,
        )

    base = make_zone(
        "interior_base", "permanent", 0, 1000,
        range(-20, 1021, 20), 10000,
    )
    reinforcement = make_zone(
        "transition", "reinforcement", 0, 200,
        range(0, 201, 20), 50000,
    )
    layout = TunnelLuminaireResult(
        tube_id="T1", luminaire=None, road_surface_type="dark_asphalt",
        rho_eff=0.07, road_width_m=9.0, tube_length_m=1000.0,
        arrangement="bilateral_sym", zones=[base, reinforcement],
    )
    params = {
        "mounting_height_m": 4.5, "maintenance_factor": 0.70,
        "arrangement": "bilateral_sym", "wall_offset_m": 0.30,
        "num_lanes": 2, "lane_width_m": 3.5,
        "shoulder_left_m": 1.0, "shoulder_right_m": 1.0,
        "traffic_direction": "one_way",
    }
    profile = compute_real_luminance_profile(layout, params, 9.0)
    base_fields = {
        round(float(field["s"])): float(field["L"])
        for field in profile["fields"]
        if field["zone_type"] == "interior_base"
    }

    # A 210 m aun llega el refuerzo; a 510 m la BASE ya debe usar su
    # campo periodico propio, no aquella L elevada reutilizada.
    assert base_fields[210] > base_fields[510] * 2.0
    assert abs(base_fields[510] - base_fields[710]) < 1e-6
