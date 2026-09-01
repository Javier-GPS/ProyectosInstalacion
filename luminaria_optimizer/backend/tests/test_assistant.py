from luminaire_optimizer.api import OptimizerChatRequest, app, optimizer_chat


def test_optimizer_chat_exposes_the_contextual_dialogue_endpoint():
    assert "/api/optimizer/chat" in {route.path for route in app.routes}
    assert OptimizerChatRequest.model_fields["message"].is_required()


def test_optimizer_chat_proposes_a_surface_diagnosis_without_changing_cad():
    response = optimizer_chat(OptimizerChatRequest(
        message="Quiero discutir la estrategia",
        context={
            "cad_filename": "lente.SLDPRT",
            "trace": {"transmission_pct": 82.0},
            "surface_energy": [{
                "surface_index": 6,
                "entry_pct": 40.0,
                "entry_incidence_mean_deg": 28.0,
                "tir_pct": 4.0,
                "exit_pct": 30.0,
            }],
        },
    ))

    assert response["proposal"]["strategy"] == "surface_diagnosis"
    assert response["proposal"]["requires_new_file"] is False


def test_optimizer_chat_marks_geometry_changes_as_new_candidates():
    response = optimizer_chat(OptimizerChatRequest(
        message="Quiero corregir la dirección de salida de la cara 7",
        context={"selected_surface_index": 6},
    ))

    assert response["proposal"]["strategy"] == "output_direction"
    assert response["proposal"]["requires_new_file"] is True


def test_optimizer_chat_accepts_an_annotated_wedge_sketch():
    response = optimizer_chat(OptimizerChatRequest(
        message="Prueba una cuña verde en la cara 7",
        image_base64="aW1hZ2U=",
        image_name="cuna-verde.png",
        context={"selected_surface_index": 6},
    ))

    assert response["proposal"]["strategy"] == "wedge_surface_trial"


def test_optimizer_chat_reports_the_current_contextual_status():
    response = optimizer_chat(OptimizerChatRequest(
        message="¿Qué estás haciendo?",
        context={"cad_filename": "lente.SLDPRT", "trace": {"transmission_pct": 84.0}, "selected_surface_index": 6},
    ))

    assert "cara seleccionada es la 7" in response["message"]
    assert "84.0%" in response["message"]


def test_optimizer_chat_creates_an_alignment_work_order():
    response = optimizer_chat(OptimizerChatRequest(
        message="Optimiza los ángulos de las caras 14 hasta 20 para alinearlas como la cara 8",
    ))

    assert response["proposal"]["strategy"] == "face_alignment"
    assert "14–20" in response["proposal"]["title"]
