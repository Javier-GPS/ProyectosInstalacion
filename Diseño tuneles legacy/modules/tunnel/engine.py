"""
SALVI Tunnel Engine - Motor principal
Orquesta todos los modulos de calculo CIE 88:2004.
Punto de entrada unico para el calculo de un tunel.
"""

from .models import (
    TunnelDesignResult, TunnelTube, Portal,
    PortalOrientation, SkyCondition, TrafficDirection,
    DataSource, DataConfidence
)
from .classification import classify_tunnel
from .design_speed import calculate_design_speed, default_friction_coefficient
from .l20_lseq_lth import (
    calculate_L20_model, calculate_L20_table,
    calculate_Lseq, calculate_Lth,
    calculate_interior_luminance, calculate_night_luminance
)
from .zones import build_zones, zones_to_dict
from .profile import build_profile, validate_profile, profile_to_chart_data
from .control import build_control_plan, export_dali, export_smartec


def run_tunnel_calculation(params: dict) -> dict:
    """
    Funcion principal del SALVI Tunnel Engine.
    Recibe los parametros del formulario y devuelve el resultado completo.
    """
    errors = []
    warnings = []

    try:
        def optional_float(key):
            value = params.get(key)
            if value in (None, ""):
                return None
            if isinstance(value, str):
                value = value.strip().replace(",", ".")
                if not value:
                    return None
            return float(value)

        # 1. EXTRAER PARAMETROS
        project_name    = params.get("project_name", "Proyecto Tunel")
        tube_id         = params.get("tube_id", "T1")
        length_m        = float(params.get("length_m", 300))
        speed_kmh       = float(params.get("speed_kmh", 80))
        traffic_veh_h   = int(params.get("traffic_veh_h", 500))
        num_lanes       = max(1, int(params.get("num_lanes", 1)))
        gradient_pct    = float(params.get("gradient_pct", 0.0))
        traffic_dir_str = params.get("traffic_direction", "one_way")
        exit_visible    = bool(params.get("exit_visible", False))
        daylight_pen    = params.get("daylight_penetration", "poor")
        orient_str      = params.get("portal_orientation", "S")
        env_type        = params.get("environment_type", "open_country_flat")
        sky_str         = params.get("sky_condition", "clear")
        wall_refl       = float(params.get("wall_reflectance", 0.4))
        has_pedestrians = bool(params.get("has_pedestrians", False))
        illuminated_road= bool(params.get("illuminated_road", False))
        curv_radius     = optional_float("curvature_radius_m")
        speed_source_str= params.get("speed_source", "user")
        l20_method      = params.get("l20_method", "model")
        lth_method      = params.get("lth_method", "k_factor")
        lth_standard    = params.get("lth_standard", "oc36_2015")
        tunnel_class    = params.get("tunnel_class", "auto")
        reaction_time_s = float(params.get("t_reaction", 2.5) or 2.5)
        friction_value  = optional_float("mu_friction")
        editable_dp     = (
            "mu_friction" in params
            or "t_reaction" in params
            or friction_value is not None
        )
        if editable_dp and friction_value is None:
            friction_value = default_friction_coefficient(speed_kmh)
        profile_stepped = bool(params.get("profile_stepped", False))
        n_steps         = int(params.get("n_steps", 4))

        # Parsear enums
        traffic_dir = TrafficDirection(traffic_dir_str)
        orientation = PortalOrientation(orient_str)
        sky_cond    = SkyCondition(sky_str)
        speed_src   = DataSource.USER

        # 2. CLASIFICACION
        classification = classify_tunnel(
            length_m=length_m,
            stopping_distance_m=0,
            exit_visible=exit_visible,
            daylight_penetration=daylight_pen,
            traffic_veh_h=traffic_veh_h,
            has_pedestrians=has_pedestrians,
            speed_kmh=speed_kmh,
            wall_reflectance=wall_refl,
            curvature_radius_m=curv_radius,
            gradient_pct=gradient_pct
        )

        # 3. VELOCIDAD Y DISTANCIA DE PARADA
        speed_result = calculate_design_speed(
            speed_kmh=speed_kmh,
            gradient_pct=gradient_pct,
            source=speed_src,
            confidence=DataConfidence.MEDIUM,
            reaction_time_s=reaction_time_s,
            friction_coefficient=friction_value,
        )
        SD_calculated = speed_result.stopping_distance_m
        SD_override = optional_float("stopping_distance_override_m")
        SD = SD_override if SD_override is not None else SD_calculated
        if SD <= 0:
            raise ValueError("La distancia de parada debe ser mayor que cero")

        # SD portal B (bidireccional): pendiente efectiva invertida
        # Si el túnel sube de A→B, el conductor que entra por B baja (más SD)
        if traffic_dir == TrafficDirection.TWO_WAY and gradient_pct != 0.0:
            speed_result_b = calculate_design_speed(
                speed_kmh=speed_kmh,
                gradient_pct=-gradient_pct,   # pendiente opuesta
                source=speed_src,
                confidence=DataConfidence.MEDIUM,
                reaction_time_s=reaction_time_s,
                friction_coefficient=friction_value,
            )
            SD_b_calculated = speed_result_b.stopping_distance_m
        else:
            speed_result_b = speed_result
            SD_b_calculated = SD_calculated
        SD_b_override = optional_float("stopping_distance_b_override_m")
        SD_b = SD_b_override if SD_b_override is not None else (
            SD if traffic_dir != TrafficDirection.TWO_WAY else SD_b_calculated
        )
        if SD_b <= 0:
            raise ValueError("La distancia de parada del portal B debe ser mayor que cero")

        # Reclasificar con SD real
        classification = classify_tunnel(
            length_m=length_m,
            stopping_distance_m=SD,
            exit_visible=exit_visible,
            daylight_penetration=daylight_pen,
            traffic_veh_h=traffic_veh_h,
            has_pedestrians=has_pedestrians,
            speed_kmh=speed_kmh,
            wall_reflectance=wall_refl,
            curvature_radius_m=curv_radius,
            gradient_pct=gradient_pct
        )

        # 4. L20
        if l20_method == "table":
            l20_result = calculate_L20_table(env_type, orientation)
        else:
            l20_result = calculate_L20_model(
                environment_type=env_type,
                orientation=orientation,
                sky_condition=sky_cond
            )
        L20_auto = l20_result.L20
        l20_override = optional_float("l20_override")
        if l20_override is not None:
            if l20_override <= 0:
                raise ValueError("L20 debe ser mayor que cero")
            l20_result.L20 = l20_override
            l20_result.method = "override"
            l20_result.note = "L20 portal A introducida manualmente por el usuario"

        # 5. LSEQ (estimacion)
        lseq_result = calculate_Lseq(
            l20_result.L20,
            method="estimated",
            override=optional_float("lseq_override"),
        )

        # 6. LTH
        lth_result = calculate_Lth(
            L20_result=l20_result,
            speed_kmh=speed_kmh,
            traffic_veh_h=traffic_veh_h,
            method=lth_method,
            Lseq_result=lseq_result if lth_method == "lseq" else None,
            qc_override=optional_float("qc_override"),
            stopping_distance_m=SD,
            tunnel_class=tunnel_class,
            num_lanes=num_lanes,
            traffic_direction=traffic_dir_str,
            mixed_traffic=has_pedestrians,
            standard=lth_standard,
            k_override=optional_float("k_lth_override"),
            contrast_observation=float(
                params.get("contrast_observation", 0.04) or 0.04
            ),
        )
        Lth = lth_result.Lth
        Lth_auto = Lth

        # 6b. LTH PORTAL B (bidireccional — orientación opuesta)
        _OPPOSITE_ORI = {
            "N":"S","NE":"SW","E":"W","SE":"NW",
            "S":"N","SW":"NE","W":"E","NW":"SE",
        }
        if traffic_dir == TrafficDirection.TWO_WAY:
            orient_b_str = _OPPOSITE_ORI.get(orient_str, orient_str)
            orientation_b = PortalOrientation(orient_b_str)
            if l20_method == "table":
                l20_b = calculate_L20_table(env_type, orientation_b)
            else:
                l20_b = calculate_L20_model(
                    environment_type=env_type,
                    orientation=orientation_b,
                    sky_condition=sky_cond
                )
            L20_b_auto = l20_b.L20
            l20_b_override = optional_float("l20_b_override")
            if l20_b_override is not None:
                if l20_b_override <= 0:
                    raise ValueError("L20 del portal B debe ser mayor que cero")
                l20_b.L20 = l20_b_override
                l20_b.method = "override"
                l20_b.note = "L20 portal B introducida manualmente por el usuario"
            lseq_b = calculate_Lseq(
                l20_b.L20,
                method="estimated",
                override=optional_float("lseq_b_override"),
            )
            lth_b_res = calculate_Lth(
                L20_result=l20_b,
                speed_kmh=speed_kmh,
                traffic_veh_h=traffic_veh_h,
                method=lth_method,
                Lseq_result=lseq_b if lth_method == "lseq" else None,
                qc_override=optional_float("qc_override"),
                stopping_distance_m=SD_b,
                tunnel_class=tunnel_class,
                num_lanes=num_lanes,
                traffic_direction=traffic_dir_str,
                mixed_traffic=has_pedestrians,
                standard=lth_standard,
                k_override=optional_float("k_lth_b_override"),
                contrast_observation=float(
                    params.get("contrast_observation", 0.04) or 0.04
                ),
            )
            Lth_b = lth_b_res.Lth
            k_factor_b = lth_b_res.k_factor
        else:
            orient_b_str = orient_str
            l20_b        = l20_result
            L20_b_auto   = L20_auto
            Lth_b        = Lth
            k_factor_b   = lth_result.k_factor
        Lth_b_auto = Lth_b

        # 7. LUMINANCIA INTERIOR Y NOCTURNA
        # La tabla CIE 88 de Lin se expresa en veh/h/carril. El formulario
        # recoge la intensidad del tubo, asi que se normaliza antes de
        # consultar la tabla.
        traffic_per_lane = float(traffic_veh_h) / max(1, num_lanes)
        Lin_auto = calculate_interior_luminance(
            speed_kmh, traffic_per_lane, length_m,
        )
        lin_override = optional_float("interior_luminance_override")
        if lin_override is not None:
            if not 0.1 <= lin_override <= 20.0:
                raise ValueError(
                    "Lin interior manual debe estar entre 0,1 y 20 cd/m²"
                )
            Lin = lin_override
            warnings.append(
                f"Lin={Lin:.2f} cd/m² fijada por criterio de proyecto "
                f"(automática CIE 88: {Lin_auto:.2f} cd/m²)."
            )
        else:
            Lin = Lin_auto

        # La consigna directa de Lth permite reproducir un proyecto existente
        # sin ocultar la referencia calculada con CIE/OC 36.
        lth_override = optional_float("lth_override")
        if lth_override is not None:
            if lth_override <= 0:
                raise ValueError("Lth manual debe ser mayor que cero")
            Lth = lth_override
            lth_result.Lth = Lth
            lth_result.k_factor = Lth / l20_result.L20
            lth_result.k_source = "project_override"
            warnings.append(
                f"Lth={Lth:.1f} cd/m² fijada por criterio de proyecto "
                f"(CIE/OC 36: {Lth_auto:.1f} cd/m²)."
            )
            if traffic_dir != TrafficDirection.TWO_WAY:
                Lth_b = Lth
                k_factor_b = lth_result.k_factor
        lth_b_override = optional_float("lth_b_override")
        if traffic_dir == TrafficDirection.TWO_WAY and lth_b_override is not None:
            if lth_b_override <= 0:
                raise ValueError("Lth manual del portal B debe ser mayor que cero")
            Lth_b = lth_b_override
            lth_b_res.Lth = Lth_b
            lth_b_res.k_factor = Lth_b / l20_b.L20
            lth_b_res.k_source = "project_override"
            k_factor_b = lth_b_res.k_factor
            warnings.append(
                f"Lth B={Lth_b:.1f} cd/m² fijada por criterio de proyecto "
                f"(CIE/OC 36: {Lth_b_auto:.1f} cd/m²)."
            )
        night_normal_override = params.get(
            "night_normal_luminance_cd_m2", None
        )
        if night_normal_override is not None:
            L_night_normal = max(0.0, float(night_normal_override))
        else:
            L_night_normal = Lin

        night_reduced_override = params.get(
            "night_reduced_luminance_cd_m2",
            params.get("night_luminance_cd_m2", None),
        )
        if night_reduced_override is not None:
            L_night_reduced = max(0.0, float(night_reduced_override))
        else:
            external_road_luminance = params.get(
                "external_road_luminance_cd_m2", None
            )
            L_night_reduced = calculate_night_luminance(
                Lin,
                illuminated_road,
                (
                    float(external_road_luminance)
                    if external_road_luminance is not None else None
                ),
                bool(params.get("reduced_night", False)),
            )
        # Compatibilidad: L_night sigue representando la escena reducida.
        L_night = L_night_reduced

        # Clase 1: la OC 36 no fija Lth. Para mantener continuo el perfil
        # computacional se usa Lin, sin convertirlo en un requisito de umbral.
        if (lth_result.tunnel_class == 1 and lth_result.k_factor == 0
                and lth_override is None):
            warnings.append(
                "Clase 1 OC 36/2015: no hay requisito de Lth; "
                "el perfil usa Lin únicamente como nivel de continuidad."
            )
            Lth = Lin
            lth_result.Lth = Lth
            if traffic_dir == TrafficDirection.TWO_WAY:
                Lth_b = Lin
                lth_b_res.Lth = Lth_b
        # Verificacion: Lth debe ser > Lin para clases con zona umbral.
        elif Lth < Lin:
            warnings.append(
                "Lth={:.1f} < Lin={:.2f} — Se usara Lin como umbral minimo".format(Lth, Lin)
            )
            Lth = max(Lth, Lin * 2)
            lth_result.Lth = Lth

        # 8. ZONAS
        threshold_length_override = optional_float("threshold_length_override_m")
        threshold_length_b_override = optional_float("threshold_length_b_override_m")
        transition_end_override = optional_float("transition_end_override_m")
        transition_end_b_override = optional_float("transition_end_b_override_m")
        exit_length_override = optional_float("exit_length_override_m")
        exit_luminance_ratio_override = optional_float(
            "exit_luminance_ratio_override"
        )
        for label, value in (
            ("Longitud de umbral", threshold_length_override),
            ("Longitud de umbral B", threshold_length_b_override),
            ("Fin de transición", transition_end_override),
            ("Fin de transición B", transition_end_b_override),
            ("Longitud de salida", exit_length_override),
        ):
            if value is not None and value <= 0:
                raise ValueError(f"{label} de proyecto debe ser mayor que cero")

        if exit_luminance_ratio_override is not None and not (
            0.0 <= exit_luminance_ratio_override <= 200.0
        ):
            raise ValueError(
                "El objetivo de salida relativo a Lin debe estar entre 0 y 200 %"
            )
        exit_luminance_ratio = (
            exit_luminance_ratio_override / 100.0
            if exit_luminance_ratio_override is not None else 1.0
        )

        zones = build_zones(
            tube_length=length_m,
            stopping_distance_m=SD,
            speed_kmh=speed_kmh,
            Lth=Lth,
            Lin=Lin,
            classification=classification,
            traffic_direction=traffic_dir,
            L_night=L_night,
            Lth_b=Lth_b,
            stopping_distance_b_m=SD_b,
            threshold_length_override_m=threshold_length_override,
            threshold_length_b_override_m=threshold_length_b_override,
            transition_end_override_m=transition_end_override,
            transition_end_b_override_m=transition_end_b_override,
            exit_length_override_m=exit_length_override,
            exit_luminance_ratio=exit_luminance_ratio,
        )
        zones.tube_id = tube_id
        # Propagar advertencias de zonas (ej. tunel corto)
        warnings.extend(zones.warnings)

        # 9. PERFIL LONGITUDINAL
        # Resolucion: 1m para tuneles <= 500m, 2m para mayores
        step_size = 1.0 if length_m <= 500 else 2.0

        profile = build_profile(
            tube_length=length_m,
            stopping_distance=SD,
            speed_kmh=speed_kmh,
            Lth=Lth,
            Lin=Lin,
            L_night=L_night,
            zones=zones,
            step_size=step_size,
            use_stepped=profile_stepped,
            n_steps_transition=n_steps,
            Lth_b=Lth_b,
        )

        # 10. VALIDACION
        validation = validate_profile(profile)
        errors.extend(validation.get("errors", []))
        warnings.extend(validation.get("warnings", []))

        # 11. DATOS PARA GRAFICA
        chart_data = profile_to_chart_data(profile)

        # 12. PLAN DE CONTROL
        n_tr_groups = int(params.get("n_transition_groups", 2))
        ctrl_protocol = params.get("control_protocol", "DALI")
        exterior_config = params.get("luminaire", {}) or {}
        if not isinstance(exterior_config, dict):
            exterior_config = {}
        control_plan = build_control_plan(
            tube_id=tube_id,
            L20_design=l20_result.L20,
            Lth_design=Lth,
            Lin=Lin,
            L_night=L_night,
            L_night_normal=L_night_normal,
            k_factor=lth_result.k_factor,
            speed_kmh=speed_kmh,
            zones=zones,
            n_transition_groups=n_tr_groups,
            protocol=ctrl_protocol,
            L20_design_b=l20_b.L20,
            Lth_design_b=Lth_b,
            k_factor_b=k_factor_b,
            driver_min_dim_pct=float(
                params.get("driver_min_dim_pct", 0.1)
            ),
            scene_factors=params.get("control_scene_factors"),
            exterior_enabled=bool(
                exterior_config.get("daylight_contribution_enabled", False)
                or exterior_config.get("exterior_layer_enabled", False)
            ),
            exterior_portal_a=bool(
                exterior_config.get(
                    "daylight_portal_a",
                    exterior_config.get("exterior_portal_a", True),
                )
            ),
            exterior_portal_b=bool(
                exterior_config.get(
                    "daylight_portal_b",
                    exterior_config.get("exterior_portal_b", True),
                )
            ),
            exterior_mouth_contribution_pct=float(
                exterior_config.get(
                    "daylight_mouth_contribution_pct",
                    exterior_config.get(
                        "exterior_mouth_contribution_pct", 10.0,
                    ),
                ) or 0.0
            ),
            exterior_penetration_length_m=float(
                exterior_config.get(
                    "daylight_penetration_length_m",
                    exterior_config.get("exterior_length_m", 60.0),
                ) or 0.0
            ),
        )
        warnings.extend(control_plan.warnings)

        # 13. RESUMEN DE RESULTADOS Y TRAZABILIDAD DE PROYECTO
        project_overrides = []
        def add_project_override(label, cie_value, project_value, unit):
            if project_value is not None:
                project_overrides.append({
                    "label": label,
                    "cie_value": round(float(cie_value), 2),
                    "project_value": round(float(project_value), 2),
                    "unit": unit,
                    "difference": round(float(project_value) - float(cie_value), 2),
                })

        add_project_override("L20 portal A", L20_auto, l20_override, "cd/m²")
        if traffic_dir == TrafficDirection.TWO_WAY:
            add_project_override("L20 portal B", L20_b_auto, l20_b_override, "cd/m²")
        add_project_override("DP portal A", SD_calculated, SD_override, "m")
        if traffic_dir == TrafficDirection.TWO_WAY:
            add_project_override("DP portal B", SD_b_calculated, SD_b_override, "m")
        add_project_override("Lth portal A", Lth_auto, lth_override, "cd/m²")
        if traffic_dir == TrafficDirection.TWO_WAY:
            add_project_override("Lth portal B", Lth_b_auto, lth_b_override, "cd/m²")
        add_project_override("Lin interior", Lin_auto, lin_override, "cd/m²")
        add_project_override(
            "Longitud umbral A", SD, threshold_length_override, "m"
        )
        if zones.transition is not None:
            add_project_override(
                "Fin transición A desde boca",
                zones.threshold.length + (zones.transition.strict_length_m or zones.transition.length),
                transition_end_override,
                "m",
            )
        if traffic_dir == TrafficDirection.TWO_WAY:
            add_project_override("Longitud umbral B", SD_b, threshold_length_b_override, "m")
            add_project_override(
                "Fin transición B desde boca",
                zones.threshold_b.length + (zones.transition_b.strict_length_m or zones.transition_b.length),
                transition_end_b_override,
                "m",
            )
        if traffic_dir != TrafficDirection.TWO_WAY:
            add_project_override("Longitud salida", SD, exit_length_override, "m")
            if (
                exit_luminance_ratio_override is not None
                and abs(exit_luminance_ratio_override - 100.0) > 1e-9
            ):
                add_project_override(
                    "L salida / Lin",
                    100.0,
                    exit_luminance_ratio_override,
                    "%",
                )
        if project_overrides:
            warnings.append(
                f"⚠ Proyecto con {len(project_overrides)} valor(es) manual(es): "
                "se muestran frente a la referencia CIE/OC 36."
            )

        # 14. RESUMEN DE RESULTADOS
        return {
            "success": True,
            "errors": errors,
            "warnings": warnings,
            "summary": {
                "project": project_name,
                "tube_id": tube_id,
                "length_m": length_m,
                "speed_kmh": speed_kmh,
                "SD_m": SD,
                "L20": round(l20_result.L20, 0),
                "Lth": round(Lth, 1),
                "Lin": round(Lin, 2),
                "Lin_auto": round(Lin_auto, 2),
                "Lin_source": (
                    "project_override" if lin_override is not None
                    else "cie88_traffic_per_lane"
                ),
                "L_night": round(L_night, 2),
                "L_night_normal": round(L_night_normal, 2),
                "L_night_reduced": round(L_night_reduced, 2),
                "Lseq": round(lseq_result.Lseq, 0),
                "k_factor": round(lth_result.k_factor, 4),
                "qc": round(lth_result.qc, 3),
            },
            "classification": {
                "geometric": classification.geometric_category.value,
                "optical": classification.optical_category.value,
                "daylighting": classification.daylighting_need.value,
                "justification": classification.justification
            },
            "speed": {
                "v_kmh": speed_kmh,
                "SD_m": SD,
                "d_reaction_m": speed_result.reaction_distance_m,
                "d_braking_m": speed_result.braking_distance_m,
                "reference_point_s": speed_result.reference_point_s,
                "SD_calculated_m": SD_calculated,
                "SD_source": (
                    "user_override"
                    if SD_override is not None
                    else speed_result.calculation_method
                ),
                "reaction_time_s": speed_result.reaction_time_s,
                "friction_coefficient": speed_result.friction_coefficient,
            },
            "l20": {
                "L20": round(l20_result.L20, 0),
                "method": l20_result.method,
                "confidence": l20_result.confidence.value,
                "note": l20_result.note
            },
            "lth": {
                "Lth": round(Lth, 1),
                "Lth_b": round(Lth_b, 1),
                "Lth_auto": round(Lth_auto, 1),
                "Lth_b_auto": round(Lth_b_auto, 1),
                "L20": round(l20_result.L20, 0),
                "L20_b": round(l20_b.L20, 0),
                "SD_b_m": round(SD_b, 1),
                "orientation_b": orient_b_str,
                "k_factor": round(lth_result.k_factor, 4),
                "qc": round(lth_result.qc, 3),
                "method": lth_result.method,
                "converged": lth_result.converged,
                "standard": lth_result.standard,
                "tunnel_class": lth_result.tunnel_class,
                "calculated_tunnel_class": lth_result.calculated_tunnel_class,
                "tunnel_class_source": lth_result.tunnel_class_source,
                "k_source": lth_result.k_source,
                "qc_used": lth_result.qc_used,
                "C_obs": lth_result.C_obs,
                "note": lth_result.note,
                "L20_source": l20_result.method,
                "Lseq_source": lseq_result.method,
                "SD_source": "user_override" if SD_override is not None else speed_result.calculation_method,
                "SD_calculated_m": SD_calculated,
                "SD_b_source": "user_override" if SD_b_override is not None else speed_result_b.calculation_method,
                "SD_b_calculated_m": SD_b_calculated
            },
            "interior": {
                "Lin": round(Lin, 2),
                "Lin_auto": round(Lin_auto, 2),
                "Lin_source": (
                    "project_override" if lin_override is not None
                    else "cie88_traffic_per_lane"
                ),
                "traffic_per_lane_veh_h": round(traffic_per_lane, 1),
                "L_night": round(L_night, 2),
                "L_night_normal": round(L_night_normal, 2),
                "L_night_reduced": round(L_night_reduced, 2),
                "night_normal_source": (
                    "user_override"
                    if night_normal_override is not None
                    else "interior_design_Lin"
                ),
                "night_reduced_source": (
                    "user_override"
                    if night_reduced_override is not None
                    else "calculated_night_level"
                ),
            },
            "zones": zones_to_dict(zones),
            "project_overrides": {
                "has_overrides": bool(project_overrides),
                "items": project_overrides,
                "note": (
                    "Valores de proyecto aplicados. La referencia CIE/OC 36 "
                    "se conserva para comparación; el perfil y la fotometría "
                    "usan el valor de proyecto."
                ),
            },
            "profile": profile.to_dict(),
            "chart": chart_data,
            "validation": validation,
            "control": control_plan.to_dict(),
            "quality_criteria": {
                "Uo_min": 0.40,
                "Ul_min": 0.60,
                "TI_max": 15.0,
                "wall_ratio_min": 0.60,
                "note": "Criterios de uniformidad y deslumbramiento requieren calculo fotometrico completo con LDT"
            }
        }

    except Exception as e:
        import traceback
        return {
            "success": False,
            "errors": [str(e)],
            "warnings": warnings,
            "traceback": traceback.format_exc()
        }
