#!/usr/bin/env python3
"""AI assistant — Q&A about SALVI Solar Studio projects, via the Anthropic Messages API."""
import os, json
import requests

ANTHROPIC_URL = 'https://api.anthropic.com/v1/messages'
DEFAULT_MODEL = os.environ.get('SALVI_AI_MODEL', 'claude-haiku-4-5-20251001')

SYSTEM_PROMPT = (
    "Eres el asistente de SALVI Solar Studio, una herramienta de dimensionado de farolas "
    "solares autonomas (panel fotovoltaico + bateria + LED + gestion Smartec). El usuario es "
    "un ingeniero o comercial de C.M. SALVI. Se te da como contexto en JSON el proyecto "
    "actualmente abierto en la app (ubicacion, fotometria, perfil nocturno, entorno/soiling, "
    "y si ya se ha ejecutado, los resultados de simulacion: candidatos, produccion, bateria, "
    "coste/TCO, correccion por sombras) y la lista de proyectos guardados por el usuario en su "
    "navegador. Responde en espanol, de forma breve y concreta, citando cifras del contexto "
    "cuando esten disponibles. Si te preguntan algo que los datos no permiten responder, dilo "
    "claramente en vez de inventar cifras."
)


def ask_question(question, context, history=None):
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return {'error': 'ANTHROPIC_API_KEY no configurada en el servidor. Anadela al archivo .env (ver .env.example) y reinicia el backend.'}

    messages = []
    for turn in (history or []):
        role, content = turn.get('role'), turn.get('content')
        if role in ('user', 'assistant') and content:
            messages.append({'role': role, 'content': content})

    context_block = json.dumps(context or {}, ensure_ascii=False, default=str)
    messages.append({
        'role': 'user',
        'content': f"Contexto de proyectos (JSON):\n{context_block}\n\nPregunta: {question}",
    })

    try:
        r = requests.post(
            ANTHROPIC_URL,
            headers={
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json',
            },
            json={
                'model': DEFAULT_MODEL,
                'max_tokens': 1024,
                'system': SYSTEM_PROMPT,
                'messages': messages,
            },
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        text = ''.join(b.get('text', '') for b in data.get('content', []) if b.get('type') == 'text')
        return {'answer': text.strip() or '(respuesta vacia)'}
    except requests.exceptions.HTTPError as exc:
        detail = ''
        try:
            detail = exc.response.json().get('error', {}).get('message', '')
        except Exception:
            pass
        return {'error': f'Error llamando a la IA: {detail or exc}'}
    except Exception as exc:
        return {'error': f'Error llamando a la IA: {exc}'}
