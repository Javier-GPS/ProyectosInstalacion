"""Anthropic AI proxy service."""
import json
import os
import urllib.error as _ue
import urllib.request as _ur


def ask_claude(question: str, context: str, api_key: str = "", model: str = "") -> dict:
    """Send a question to Claude and return the answer."""
    _AI_KEY = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not _AI_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")
    _AI_MODEL = model or os.environ.get("SALVI_AI_MODEL", "claude-haiku-4-5-20251001")

    prompt = f"""{context}

PREGUNTA DEL USUARIO: {question}

Responde de forma clara y concisa, usando datos del proyecto cuando sea relevante.
Si no tienes suficiente información, dilo directamente.
"""
    body_json = json.dumps({
        "model": _AI_MODEL,
        "max_tokens": 2000,
        "system": "Eres un asistente experto en alumbrado publico que analiza proyectos de iluminacion urbana.",
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = _ur.Request(
        "https://api.anthropic.com/v1/messages", data=body_json,
        headers={"Content-Type": "application/json", "x-api-key": _AI_KEY,
                 "anthropic-version": "2023-06-01"},
    )
    try:
        with _ur.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            answer = data["content"][0]["text"]
            usage = data.get("usage", {})
            return {"answer": answer, "usage": usage, "context": context}
    except _ue.HTTPError as e:
        raise RuntimeError(f"API error {e.code}: {e.read().decode('utf-8', 'replace')}")
