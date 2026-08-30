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
            "Puedo discutir la estrategia antes de ejecutar nada. Indícame qué quieres "
            "priorizar: dirección de salida, transmisión, reducción de TIR, una cara concreta "
            "o un barrido de parámetros. La geometría original quedará protegida."
        ),
        "proposal": None,
    }
