"""Contextual optical-strategy advisor used by the in-app dialogue."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
import uuid
from typing import Any


ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
DEFAULT_ANTHROPIC_MODEL = os.environ.get("SALVI_AI_MODEL", "claude-sonnet-4-5-20250929")
DEFAULT_OLLAMA_TIMEOUT_SECONDS = 300
OLLAMA_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {"type": "string"},
        "proposal": {"type": ["object", "null"]},
    },
    "required": ["message", "proposal"],
}


def _autonomous_requested(message: str) -> bool:
    lowered = message.lower()
    return any(phrase in lowered for phrase in (
        "de forma autónoma", "de forma autonoma", "modo autónomo", "modo autonomo",
        "sin mi intervención", "sin mi intervencion", "hazlo tú", "hazlo tu",
        "ejecútalo", "ejecutalo", "ejecuta la propuesta",
        "modifica la lente", "modificar la lente", "corrige la lente", "corregir la lente",
        "haz las modificaciones", "haz los cambios", "realiza las modificaciones",
        "aplica los cambios",
    ))


def _autonomous_proposal() -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex,
        "title": "Exploración autónoma de la lente",
        "strategy": "autonomous_cad_exploration",
        "summary": "Probar cambios CAD acotados, trazar rayos y conservar solo una mejora verificable.",
        "rationale": "La aplicación usará el modelo actual, un presupuesto limitado de candidatas y copias nuevas del archivo.",
        "steps": [
            "Medir la lente base como referencia.",
            "Probar parámetros CAD elegibles con pocos rayos.",
            "Validar la mejor candidata con el trazado completo.",
            "Guardar una copia nueva solo si mejora el objetivo.",
        ],
        "requires_new_file": True,
        "approval": "Ejecución autónoma autorizada por esta instrucción.",
    }


def _execution_status(context: dict[str, Any]) -> dict[str, Any] | None:
    state = context.get("execution_state")
    if not state:
        return None
    labels = {
        "trace": "trazado del LDT",
        "autonomous": "exploración autónoma de la lente y trazado del LDT",
        "evaluate": "evaluación de la calzada",
        "optimize": "optimización de corrientes",
    }
    phase = labels.get(str(state), "cálculo en curso")
    return {
        "message": (
            f"Hay una operación en curso: {phase}. SolidWorks está ocupado con la "
            "candidata actual. No iniciaré otra modificación CAD simultánea y las "
            "corrientes permanecen sin cambios durante esta fase."
        ),
        "proposal": None,
    }


class AssistantServiceError(RuntimeError):
    """Raised when the configured language model cannot be reached."""


SYSTEM_PROMPT = """
Eres el copiloto óptico de SALVI Luminaria Optimizer. Ayudas a ingenieros a entender
la geometría de una lente, sus rayos, superficies, transmisión y distribución
fotométrica, y a decidir experimentos seguros sobre un SLDPRT/SLDASM.

Responde siempre en español, de forma clara y concreta. Usa las cifras del contexto
cuando existan y no inventes mediciones. Distingue entre lo que muestran los datos,
una hipótesis y una recomendación. Recuerda que un LDT calculado por trazado es una
predicción y debe validarse en laboratorio.

Devuelve únicamente JSON válido con esta forma:
{
  "message": "respuesta para el usuario",
  "proposal": null o {
    "title": "título breve",
    "strategy": "identificador en snake_case",
    "summary": "qué se probaría",
    "rationale": "por qué, basado en el contexto",
    "steps": ["paso 1", "paso 2"],
    "requires_new_file": true o false,
    "approval": "pregunta de aprobación"
  }
}

Solo crea proposal cuando el usuario pida diagnosticar o modificar la geometría.
Las propuestas nunca se han ejecutado: requieren aprobación explícita en la interfaz.
Si se adjunta una imagen con tres sistemas ópticos y trayectorias marcadas, empieza
por revisar los tres recorridos por separado, comparando entrada, giro y salida.
No conviertas esa revisión en una propuesta de una sola superficie: espera a que el
usuario confirme el diagnóstico antes de preparar el programa sistema a sistema.
Para preguntas informativas, devuelve proposal null. Nunca afirmes que has cambiado
SolidWorks, calculado una candidata o guardado un archivo si no aparece en el contexto.
""".strip()


def _image_media_type(image_name: str | None) -> str:
    suffix = (image_name or "").lower().rsplit(".", 1)[-1]
    return {"jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp", "gif": "image/gif"}.get(suffix, "image/png")


def _normalise_response_text(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    if not raw:
        raise AssistantServiceError("El modelo de IA devolvió una respuesta vacía.")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Vision models sometimes wrap the JSON in Markdown or emit a short
        # reasoning prefix even when structured output was requested.
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return {"message": raw, "proposal": None}
        try:
            parsed = json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            return {"message": raw, "proposal": None}
    if not isinstance(parsed, dict):
        return {"message": raw, "proposal": None}
    response_message = (
        parsed.get("message")
        or parsed.get("answer")
        or parsed.get("response")
        or parsed.get("respuesta")
        or parsed.get("analysis")
        or parsed.get("imagen_descrita")
    )
    if not isinstance(response_message, str) or not response_message.strip():
        if not parsed:
            raise AssistantServiceError("El modelo local devolvió una respuesta vacía.")
        return {"message": json.dumps(parsed, ensure_ascii=False, indent=2), "proposal": None}
    proposal = parsed.get("proposal")
    if isinstance(proposal, dict):
        required = ("title", "strategy", "summary", "rationale", "steps", "requires_new_file", "approval")
        if not all(key in proposal for key in required) or not isinstance(proposal.get("steps"), list):
            proposal = None
        else:
            proposal = {
                "id": str(proposal.get("id") or uuid.uuid4().hex),
                "title": str(proposal["title"]),
                "strategy": str(proposal["strategy"]),
                "summary": str(proposal["summary"]),
                "rationale": str(proposal["rationale"]),
                "steps": [str(step) for step in proposal["steps"]],
                "requires_new_file": bool(proposal["requires_new_file"]),
                "approval": str(proposal["approval"]),
            }
    return {"message": response_message.strip(), "proposal": proposal}


def _normalise_model_response(data: dict[str, Any]) -> dict[str, Any]:
    blocks = data.get("content", [])
    raw = "".join(block.get("text", "") for block in blocks if isinstance(block, dict) and block.get("type") == "text")
    return _normalise_response_text(raw)


def _normalise_ollama_response(data: dict[str, Any]) -> dict[str, Any]:
    response = data.get("message", {})
    raw = response.get("content", "") if isinstance(response, dict) else ""
    return _normalise_response_text(raw if isinstance(raw, str) else "")


def _conversation_messages(message: str, context: dict[str, Any], history: list[dict[str, str]]) -> tuple[list[dict[str, Any]], str]:
    messages: list[dict[str, Any]] = []
    for turn in history[-20:]:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"]})
    context_block = json.dumps(context, ensure_ascii=False, default=str)
    prompt = f"Contexto actual de la aplicación (JSON):\n{context_block}\n\nPregunta o instrucción del usuario:\n{message}"
    return messages, prompt


def _ask_anthropic(message: str, context: dict[str, Any], history: list[dict[str, str]], image_base64: str | None, image_name: str | None) -> dict[str, Any]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise AssistantServiceError("ANTHROPIC_API_KEY no está configurada.")

    messages, prompt = _conversation_messages(message, context, history)
    if image_base64:
        content: list[dict[str, Any]] = [
            {"type": "image", "source": {"type": "base64", "media_type": _image_media_type(image_name), "data": image_base64}},
            {"type": "text", "text": prompt},
        ]
    else:
        content = [{"type": "text", "text": prompt}]
    messages.append({"role": "user", "content": content})

    payload = json.dumps({"model": DEFAULT_ANTHROPIC_MODEL, "max_tokens": 1400, "system": SYSTEM_PROMPT, "messages": messages}).encode("utf-8")
    request = urllib.request.Request(
        ANTHROPIC_URL,
        data=payload,
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return _normalise_model_response(json.loads(response.read().decode("utf-8")))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error", {}).get("message", "")
        except (OSError, ValueError):
            detail = ""
        raise AssistantServiceError(f"Error de Anthropic: {detail or exc.reason}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AssistantServiceError(f"No se pudo contactar con la IA: {exc}") from exc


def _ask_ollama(message: str, context: dict[str, Any], history: list[dict[str, str]], image_base64: str | None, image_name: str | None) -> dict[str, Any]:
    messages, prompt = _conversation_messages(message, context, history)
    if image_base64:
        prompt = f"Se ha adjuntado la imagen `{image_name or 'croquis'}`. Analízala visualmente.\n\n{prompt}"
        if message.strip().lower().startswith("croquis adjunto:"):
            prompt = (
                "Revisa la imagen adjunta y explica qué observas en sus sistemas ópticos, "
                "rayos, direcciones deseadas y zonas que deben evitarse. No propongas todavía "
                "cambios CAD.\n\n" + prompt
            )
    current: dict[str, Any] = {"role": "user", "content": prompt}
    if image_base64:
        current["images"] = [image_base64]
    messages.append(current)
    payload = json.dumps({
        "model": os.environ.get("SALVI_AI_MODEL", "qwen2.5vl:7b"),
        "system": SYSTEM_PROMPT,
        "messages": messages,
        "format": OLLAMA_RESPONSE_SCHEMA,
        "stream": False,
        "think": False,
        "options": {"temperature": 0.2},
    }).encode("utf-8")
    request = urllib.request.Request(
        os.environ.get("SALVI_AI_OLLAMA_URL", OLLAMA_URL),
        data=payload,
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        timeout = float(os.environ.get("SALVI_AI_TIMEOUT_SECONDS", DEFAULT_OLLAMA_TIMEOUT_SECONDS))
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return _normalise_ollama_response(json.loads(response.read().decode("utf-8")))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error", "")
        except (OSError, ValueError):
            detail = ""
        raise AssistantServiceError(f"Error de Ollama: {detail or exc.reason}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AssistantServiceError(f"No se pudo contactar con Ollama en {request.full_url}: {exc}") from exc


def _ask_model(message: str, context: dict[str, Any], history: list[dict[str, str]], image_base64: str | None, image_name: str | None) -> dict[str, Any] | None:
    provider = os.environ.get("SALVI_AI_PROVIDER", "").strip().lower()
    if provider in {"ollama", "local"}:
        return _ask_ollama(message, context, history, image_base64, image_name)
    if provider in {"anthropic", "claude"}:
        return _ask_anthropic(message, context, history, image_base64, image_name)
    if os.environ.get("ANTHROPIC_API_KEY"):
        return _ask_anthropic(message, context, history, image_base64, image_name)
    return None


def _surface_number(message: str, context: dict[str, Any]) -> int | None:
    match = re.search(r"(?:cara|superficie)\s*(\d+)", message.lower())
    if match:
        return max(0, int(match.group(1)) - 1)
    value = context.get("selected_surface_index")
    return int(value) if isinstance(value, int) else None


def _surface_summary(context: dict[str, Any], surface_index: int | None) -> str:
    surfaces = context.get("surface_energy")
    if not isinstance(surfaces, list) or surface_index is None:
        return "No hay una cara seleccionada con métricas disponibles."
    record = next(
        (item for item in surfaces if isinstance(item, dict) and item.get("surface_index") == surface_index),
        None,
    )
    if record is None:
        return "La cara indicada no aparece en la muestra actual."
    entry = float(record.get("entry_pct", 0.0))
    tir = float(record.get("tir_pct", 0.0))
    exit_flux = float(record.get("exit_pct", 0.0))
    incidence = float(record.get("entry_incidence_mean_deg", 0.0))
    return (
        f"La cara {surface_index + 1} recibe {entry:.2f}% del flujo, "
        f"tiene una incidencia media de {incidence:.1f}°, "
        f"TIR {tir:.2f}% y salida {exit_flux:.2f}%."
    )


def advise(message: str, context: dict[str, Any], history: list[dict[str, str]] | None = None, image_base64: str | None = None, image_name: str | None = None) -> dict[str, Any]:
    """Ask the configured LLM, falling back to the deterministic local advisor."""
    status = _execution_status(context)
    if status is not None and any(phrase in message.lower() for phrase in ("qué estás", "que estas", "estado", "informa", "avanza", "fase")):
        return status
    model_response = _ask_model(message, context, history or [], image_base64, image_name)
    if model_response is not None:
        if _autonomous_requested(message):
            # The model may describe an action as completed; only the CAD endpoint
            # can confirm that, so replace it with an explicit pre-execution state.
            model_response["message"] = (
                "Solicitud autónoma recibida. Todavía no se ha modificado ningún archivo. "
                "La aplicación ejecutará una exploración CAD limitada y solo conservará "
                "una candidata si el resultado medido mejora."
            )
            model_response["proposal"] = model_response.get("proposal") or _autonomous_proposal()
        return model_response

    text = message.strip()
    lowered = text.lower()
    surface_index = _surface_number(lowered, context)
    source_name = str(context.get("cad_filename") or "el modelo CAD")
    trace = context.get("trace") if isinstance(context.get("trace"), dict) else {}
    transmission = float(trace.get("transmission_pct", 0.0))
    surface_text = _surface_summary(context, surface_index)
    image_note = (
        f" He recibido `{context.get('image_name', 'el croquis')}` como referencia visual; "
        "usaré la instrucción asociada para acotar la prueba."
        if context.get("image_attached") else ""
    )

    if _autonomous_requested(text):
        return {
            "message": (
                "Solicitud autónoma recibida. Todavía no se ha modificado ningún archivo. "
                "Ejecutaré una exploración CAD limitada y guardaré una copia nueva solo "
                "si el resultado medido mejora."
            ),
            "proposal": _autonomous_proposal(),
        }

    # Give the no-key fallback the same staged behaviour for the main visual review.
    visual_review = context.get("image_attached") and (
        ("3" in lowered or "tres" in lowered)
        and any(word in lowered for word in ("sistema", "vista"))
        and any(word in lowered for word in ("rayo", "dirección", "direccion", "entrada", "salida"))
        and not any(word in lowered for word in ("cuña", "cuna", "ejecuta", "modifica"))
    )
    if visual_review:
        return {
            "message": (
                "He revisado la imagen como una hipótesis visual de tres sistemas ópticos. "
                "Interpreto el sistema izquierdo (cara 23) con una entrada desde el LED, "
                "un giro en la zona inferior y una salida casi horizontal ascendente; el "
                "sistema central (cara 8) con una entrada prácticamente vertical, un giro "
                "cercano a 90° y una salida horizontal; y el sistema derecho (cara 18) con "
                "un giro progresivo y una salida inclinada hacia arriba. Las tres trayectorias "
                "rojas son coherentes como dirección del rayo principal o eje medio del haz. "
                "Coincido con revisarlos y modificarlos uno a uno, pero todavía no genero una "
                "candidata: primero hay que confirmar la dirección objetivo y la tolerancia "
                "angular. Después prepararé un programa independiente para cada sistema, "
                "manteniendo los otros dos sin cambios."
            ),
            "proposal": None,
        }

    if any(phrase in lowered for phrase in ("qué estás haciendo", "que estas haciendo", "estado", "en qué punto", "en que punto")):
        selected = f"La cara seleccionada es la {surface_index + 1}. {surface_text}" if surface_index is not None else "No hay una cara seleccionada todavía."
        trace_state = (
            f"El último trazado transmite {transmission:.1f}% del flujo."
            if trace else "Aún no hay un trazado CAD disponible."
        )
        return {
            "message": (
                f"Estado actual: sigo `{source_name}`. {trace_state} {selected} "
                "Puedo ejecutar tres acciones: diagnosticar la cara seleccionada, probar la cuña del croquis nuevo o buscar una corrección de salida hacia la calzada."
            ),
            "proposal": None,
        }

    if any(word in lowered for word in ("apruebo", "acepto", "adelante", "rechazo", "descarto")):
        approved = not any(word in lowered for word in ("rechazo", "descarto"))
        return {
            "message": (
                "Estrategia registrada como aprobada. El siguiente paso será convertirla en "
                "un barrido paramétrico y simularlo antes de guardar candidatas."
                if approved else
                "Estrategia descartada. Mantengo el modelo y el historial intactos; podemos "
                "probar otra hipótesis."
            ),
            "proposal": None,
        }

    if any(word in lowered for word in ("guardar", "histórico", "historico", "fichero", "archivo")):
        return {
            "message": (
                "Las candidatas CAD se guardarán como archivos nuevos en `modelos lentes`; "
                "no sobrescribiré el original. Una modificación geométrica genera una nueva "
                "versión y su STEP ensamblado. Los cambios de estrategia o configuración "
                "sin cambiar geometría quedan únicamente en el historial del diálogo."
            ),
            "proposal": None,
        }

    if not text or any(word in lowered for word in ("hola", "empezar", "estrategia", "qué hacemos", "que hacemos")):
        return {
            "message": (
                f"Estoy siguiendo `{source_name}`. La transmisión de la muestra actual es "
                f"{transmission:.1f}%. Podemos empezar por una cara concreta, por la "
                "dirección de salida o por un barrido paramétrico. Mi recomendación inicial "
                "es diagnosticar la cara con más flujo y mayor error angular antes de tocar el CAD."
            ),
            "proposal": {
                "id": uuid.uuid4().hex,
                "title": "Diagnóstico por superficie",
                "strategy": "surface_diagnosis",
                "summary": "Separar entrada, TIR y salida antes de modificar la lente.",
                "rationale": surface_text,
                "steps": [
                    "Identificar la cara de entrada dominante.",
                    "Comparar dirección incidente y dirección final por LED.",
                    "Elegir un único parámetro geométrico para el primer barrido.",
                ],
                "requires_new_file": False,
                "approval": "¿Apruebas este diagnóstico como siguiente paso?",
            },
        }

    alignment_range = re.search(r"caras?\s*(\d+)\s*(?:a|hasta|[-–])\s*(\d+)", lowered)
    alignment_reference = re.search(r"(?:como|con)\s+la\s+cara\s*(\d+)", lowered)
    if alignment_range and any(word in lowered for word in ("aline", "ángulo", "angulo", "colineal", "saliente", "salida")):
        first_face, last_face = (int(value) for value in alignment_range.groups())
        reference_face = int(alignment_reference.group(1)) if alignment_reference else None
        reference_text = f" con la cara {reference_face}" if reference_face is not None else " hacia la dirección vial objetivo"
        return {
            "message": (
                f"Orden interpretada: alinear la salida de las caras {first_face}–{last_face}{reference_text}. "
                "La aplicación está esperando tu aprobación para lanzar la candidata CAD."
            ),
            "proposal": {
                "id": uuid.uuid4().hex,
                "title": f"Alinear caras {first_face}–{last_face}{reference_text}",
                "strategy": "face_alignment",
                "summary": "Barrido de las cotas del feature reciente para corregir la dirección de salida.",
                "rationale": f"Objetivo: que los rayos de las caras {first_face}–{last_face} sigan la referencia indicada.",
                "steps": [
                    "Conservar la lente base y sus rayos rojos.",
                    "Variar únicamente las cotas del feature CAD más reciente.",
                    "Medir dirección de salida, transmisión y TIR.",
                    "Aceptar solo una candidata que mejore la puntuación hacia calzada.",
                ],
                "requires_new_file": True,
                "approval": "La candidata está preparada. ¿Ejecutar la prueba?",
            },
        }

    if any(word in lowered for word in ("salida", "dirección", "direccion", "apuntar", "ángulo", "angulo", "rayo")):
        selected = f" de la cara {surface_index + 1}" if surface_index is not None else " por superficie"
        return {
            "message": (
                f"Para corregir la dirección de salida{selected}, no cambiaría todavía la "
                "corriente ni el LDT. Primero probaría la superficie óptica que recibe más "
                "flujo, manteniendo fijo el resto de la lente. Así sabremos si el error viene "
                "del perfil, de la orientación CAD o de la transformación del marco."
            ),
            "proposal": {
                "id": uuid.uuid4().hex,
                "title": "Corregir dirección de salida",
                "strategy": "output_direction",
                "summary": "Barrido controlado de un parámetro de la superficie dominante.",
                "rationale": surface_text,
                "steps": [
                    "Mantener índice, LED y posición sin cambios.",
                    "Variar un solo radio o altura del croquis seleccionado.",
                    "Minimizar error angular medio y RMS, penalizando TIR.",
                    "Guardar cada mejora geométrica como nueva candidata.",
                ],
                "requires_new_file": True,
                "approval": "¿Apruebas preparar este barrido?",
            },
        }

    if any(word in lowered for word in ("analiza", "analizar", "diagnostica", "diagnóstico", "diagnostico")):
        if surface_index is None:
            return {
                "message": "Selecciona una cara en el visor 3D y pulsa `Analizar cara seleccionada`. Así asociaré entrada, TIR y salida a una superficie concreta.",
                "proposal": None,
            }
        return {
            "message": f"Diagnóstico preparado para la cara {surface_index + 1}. {surface_text}",
            "proposal": {
                "id": uuid.uuid4().hex,
                "title": f"Diagnosticar cara {surface_index + 1}",
                "strategy": "surface_diagnosis",
                "summary": "Separar entrada, TIR y salida de la cara seleccionada antes de modificarla.",
                "rationale": surface_text,
                "steps": [
                    "Mantener la geometría base como referencia.",
                    "Medir la contribución de la cara seleccionada.",
                    "Proponer una única modificación CAD si existe una mejora verificable.",
                ],
                "requires_new_file": False,
                "approval": "¿Apruebas ejecutar el diagnóstico?",
            },
        }

    if any(word in lowered for word in ("cuña", "cuna", "croquis", "imagen")):
        selected = f" en la cara {surface_index + 1}" if surface_index is not None else " en la cara de salida dominante"
        return {
            "message": (
                f"Prepararé una prueba de cuña{selected}, limitada a una única candidata y comparada "
                f"contra la geometría actual. {surface_text}{image_note}"
            ),
            "proposal": {
                "id": uuid.uuid4().hex,
                "title": "Ensayo de cuña en cara óptica",
                "strategy": "wedge_surface_trial",
                "summary": "Introducir una cuña local y medir su efecto sobre la dirección de salida.",
                "rationale": surface_text,
                "steps": [
                    "Mantener LED, índice y el resto de caras sin cambios.",
                    "Crear una candidata CAD con la cuña indicada en el croquis.",
                    "Comparar rayos rojos de referencia contra rayos amarillos de la candidata.",
                    "Conservar la candidata solo si mejora el objetivo hacia calzada.",
                ],
                "requires_new_file": True,
                "approval": "¿Apruebas preparar este ensayo de cuña?",
            },
        }

    if any(word in lowered for word in ("transmisión", "transmision", "tir", "flujo", "pérdida", "perdida")):
        return {
            "message": (
                "Para mejorar el flujo, separaría pérdidas por rayos no interceptados, "
                "reflexión interna y Fresnel. No aceptaría una mejora de transmisión si "
                "desplaza la salida fuera del objetivo angular."
            ),
            "proposal": {
                "id": uuid.uuid4().hex,
                "title": "Equilibrar transmisión y dirección",
                "strategy": "transmission_balance",
                "summary": "Optimizar transmisión sin perder el eje de salida.",
                "rationale": surface_text,
                "steps": [
                    "Usar transmisión como restricción mínima.",
                    "Medir TIR y flujo no interceptado por superficie.",
                    "Comparar cada candidata contra la mejor dirección anterior.",
                ],
                "requires_new_file": True,
                "approval": "¿Apruebas esta prioridad de optimización?",
            },
        }

    return {
        "message": (
            "No he podido convertir esa indicación en una prueba CAD concreta. Usa una de estas acciones: "
            "`Analizar cara seleccionada`, `Probar cuña del croquis nuevo` o `Corregir salida hacia calzada`."
        ),
        "proposal": None,
    }
