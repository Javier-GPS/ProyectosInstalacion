import json

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


def test_optimizer_chat_sends_history_context_and_image_to_anthropic(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"content": [{"type": "text", "text": '{"message":"Respuesta contextual","proposal":null}'}]}).encode()

    captured = {}

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("luminaire_optimizer.assistant.urllib.request.urlopen", fake_urlopen)
    response = optimizer_chat(OptimizerChatRequest(
        message="¿Qué significa esta imagen?",
        history=[{"role": "user", "content": "Estoy revisando la cara 7"}],
        image_base64="aW1hZ2U=",
        image_name="croquis.jpg",
        context={"cad_filename": "lente.SLDPRT", "trace": {"transmission_pct": 84.0}},
    ))

    assert response == {"message": "Respuesta contextual", "proposal": None}
    assert captured["timeout"] == 45
    assert captured["body"]["messages"][0]["content"] == "Estoy revisando la cara 7"
    current = captured["body"]["messages"][1]["content"]
    assert current[0]["source"]["media_type"] == "image/jpeg"
    assert "lente.SLDPRT" in current[1]["text"]


def test_optimizer_chat_reviews_three_marked_optical_systems_before_proposing_changes(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    response = optimizer_chat(OptimizerChatRequest(
        message="Revisa la imagen con las vistas de los 3 sistemas ópticos, sus entradas, salidas y direcciones de los rayos.",
        image_base64="aW1hZ2U=",
        image_name="tres-sistemas.png",
    ))

    assert response["proposal"] is None
    assert "cara 23" in response["message"]
    assert "cara 8" in response["message"]
    assert "cara 18" in response["message"]
    assert "uno a uno" in response["message"]


def test_optimizer_chat_uses_local_ollama_with_the_attached_image(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"message": {"content": '{"message":"Análisis local","proposal":null}'}}).encode()

    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("SALVI_AI_PROVIDER", "ollama")
    monkeypatch.setenv("SALVI_AI_MODEL", "qwen2.5vl:7b")
    monkeypatch.setenv("SALVI_AI_TIMEOUT_SECONDS", "180")
    monkeypatch.setattr("luminaire_optimizer.assistant.urllib.request.urlopen", fake_urlopen)
    response = optimizer_chat(OptimizerChatRequest(
        message="Revisa este croquis",
        image_base64="aW1hZ2U=",
        image_name="croquis.png",
    ))

    assert response == {"message": "Análisis local", "proposal": None}
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["body"]["model"] == "qwen2.5vl:7b"
    assert captured["body"]["messages"][-1]["images"] == ["aW1hZ2U="]
    assert "required" in captured["body"]["format"]
    assert captured["timeout"] == 180
    assert captured["body"]["think"] is False


def test_response_parser_accepts_reasoning_prefix_and_alternate_message_field():
    from luminaire_optimizer.assistant import _normalise_response_text

    response = _normalise_response_text('Pensamiento breve. ```json\n{"answer":"Respuesta válida"}\n```')

    assert response == {"message": "Respuesta válida", "proposal": None}


def test_response_parser_accepts_qwen_image_description_field():
    from luminaire_optimizer.assistant import _normalise_response_text

    response = _normalise_response_text('{"imagen_descrita":"Descripción de la imagen"}')

    assert response == {"message": "Descripción de la imagen", "proposal": None}


def test_explicit_lens_modification_request_authorizes_the_cad_bridge():
    from luminaire_optimizer.assistant import _autonomous_requested

    assert _autonomous_requested("Modifica la lente siguiendo la imagen") is True


def test_status_question_does_not_wait_for_ollama_during_cad_execution():
    from luminaire_optimizer.assistant import advise

    response = advise("Explícame qué estás haciendo y cómo avanza el proceso", {
        "execution_state": "autonomous",
    })

    assert response["proposal"] is None
    assert "exploración autónoma" in response["message"]
    assert "corrientes permanecen sin cambios" in response["message"]
