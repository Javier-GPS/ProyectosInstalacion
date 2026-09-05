"""
Analisis de geometria de boca de tunel a partir de 1-2 imagenes, usando
la vision de Claude (Anthropic API) en vez de un pipeline clasico de
vision artificial (homografia/bundle adjustment) — ver
"docs/especificaciones/Especificacion_implementacion_geometria_tuneles_desde_imagenes.docx".

Cada campo de salida se ajusta al modelo minimo del documento:
{value, unit, confidence, source}. El estado (Propuesto/Validado) NO se
gestiona aqui — es responsabilidad del frontend/formulario, ya que es
un concepto de flujo de usuario, no de resultado de vision.
"""
import os
import json
import base64
import mimetypes

ANTHROPIC_MODEL = "claude-sonnet-5"

# Campos minimos que debe intentar rellenar el analisis (seccion 9 del documento).
PORTAL_FIELD_SCHEMA = {
    "num_lanes":          {"unit": "entero",     "critical": True},
    "lane_width_m":        {"unit": "m",          "critical": True},
    "shoulder_left_m":     {"unit": "m",          "critical": True},
    "shoulder_right_m":    {"unit": "m",          "critical": True},
    "width_m":             {"unit": "m",          "critical": True},
    "tunnel_shape":        {"unit": "enum",       "critical": True},
    "height_m":            {"unit": "m",          "critical": True},
    "H_pared_m":           {"unit": "m",          "critical": True},
    "mounting_height_m":   {"unit": "m",          "critical": True},
    "num_luminaire_rows":  {"unit": "entero",     "critical": True},
    "wall_offset_m":       {"unit": "m",          "critical": True},
    "axis_offset_m":       {"unit": "m con signo", "critical": False},
    "sidewalk_present":    {"unit": "boolean",    "critical": False},
    "sidewalk_width_m":    {"unit": "m",          "critical": False},
}

CRITICAL_FIELDS = [k for k, v in PORTAL_FIELD_SCHEMA.items() if v["critical"]]


def _build_prompt(lane_width_ref_m: float) -> str:
    fields_desc = "\n".join(f"- {k} ({v['unit']})" for k, v in PORTAL_FIELD_SCHEMA.items())
    return f"""Eres un ingeniero de iluminacion de tuneles. Analiza la(s) imagen(es) adjunta(s)
de la boca de un tunel de carretera y propon la geometria de la seccion transversal.

CALIBRACION: el usuario confirma que el carril de referencia visible en la imagen
mide {lane_width_ref_m:.2f} m de ancho real. Usa esa referencia para escalar
cualquier otra medida (anchuras, alturas, offsets) — NO inventes una escala distinta.

Si se adjuntan dos imagenes, trata la boca como una sola escena: usa la imagen
mas lejana para carriles/eje/perspectiva general y la mas cercana para contorno
y luminarias, y consolida una unica propuesta coherente.

Debes proponer estos campos (usa exactamente estas claves):
{fields_desc}

tunnel_shape debe ser uno de: "horseshoe", "circular", "rectangular".

Para CADA campo que puedas estimar con evidencia visual razonable, da:
- value: el valor numerico o string (usa null si no hay evidencia suficiente)
- confidence: "alta", "media" o "baja"
- reasoning: una frase breve explicando en que te basas (marcas de carril, hastial visible, luminaria visible, etc.)

REGLA CRITICA: si no tienes evidencia visual suficiente para un campo, pon value=null
y confidence="baja". NUNCA inventes una medida sin base visual — es preferible dejar
el campo vacio a proponer un numero sin fundamento.

Responde EXCLUSIVAMENTE con un objeto JSON con esta forma exacta, sin texto adicional
antes ni despues, sin bloques de codigo markdown:

{{
  "fields": {{
    "<campo>": {{"value": <valor o null>, "confidence": "alta|media|baja", "reasoning": "..."}},
    ...
  }},
  "warnings": ["aviso1", "aviso2", ...]
}}

En "warnings" incluye cualquier caso limite detectado: boca parcialmente oculta,
imagen muy oblicua, interior subexpuesto, carril de referencia poco claro,
mas de una calzada visible, posible efecto de stitching/compresion de Street View, etc.
"""


def _image_to_block(file_path: str) -> dict:
    mime, _ = mimetypes.guess_type(file_path)
    mime = mime or "image/jpeg"
    with open(file_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": mime, "data": data},
    }


def analyze_portal_images(image_paths: list, lane_width_ref_m: float = 3.5) -> dict:
    """
    Llama a la API de Anthropic (vision) con 1-2 imagenes de una boca de tunel
    y devuelve la propuesta de geometria estructurada.

    Lanza RuntimeError con un mensaje claro (no una excepcion generica) si no
    hay ANTHROPIC_API_KEY configurada, para que el frontend pueda mostrar un
    aviso util en vez de un error opaco.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY no configurada. Anade tu clave de "
            "console.anthropic.com al archivo .env del proyecto "
            "(ANTHROPIC_API_KEY=sk-ant-...) y reinicia el servidor."
        )
    if not image_paths:
        raise ValueError("Se requiere al menos una imagen.")
    if len(image_paths) > 2:
        image_paths = image_paths[:2]

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    content = [_image_to_block(p) for p in image_paths]
    content.append({"type": "text", "text": _build_prompt(lane_width_ref_m)})

    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": content}],
    )

    raw_text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )
    raw_text = raw_text.strip()
    if response.stop_reason == "max_tokens":
        raise RuntimeError(
            "La respuesta de vision se corto por limite de tokens antes de completar el JSON. "
            "Vuelve a intentarlo (el limite ya se ha ampliado)."
        )
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"La respuesta de vision no es JSON valido: {e}. Respuesta cruda: {raw_text[:500]}"
        )

    fields_out = parsed.get("fields", {})
    for key, meta in PORTAL_FIELD_SCHEMA.items():
        if key not in fields_out:
            fields_out[key] = {"value": None, "confidence": "baja", "reasoning": "Sin dato del modelo."}
        fields_out[key]["unit"] = meta["unit"]
        fields_out[key]["critical"] = meta["critical"]

    return {
        "fields": fields_out,
        "warnings": parsed.get("warnings", []),
        "model": ANTHROPIC_MODEL,
        "lane_width_ref_m": lane_width_ref_m,
        "n_images": len(image_paths),
    }
