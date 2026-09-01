"""Contextual optical-strategy advisor used by the in-app dialogue."""
from __future__ import annotations

import re
import uuid
from typing import Any


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


def advise(message: str, context: dict[str, Any]) -> dict[str, Any]:
    """Return a local domain-specific response and an optional structured plan."""
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
