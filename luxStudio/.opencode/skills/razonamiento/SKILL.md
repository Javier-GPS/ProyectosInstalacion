---
name: razonamiento
description: Método estructurado para analizar, diseñar, depurar y revisar sin inventar evidencia
---

# Método de razonamiento estructurado

`RL1` en `.opencode/agent/razonador.md` es la fuente de estados y cierre. Esta skill define
el método, no un ledger paralelo.

## Pasos

1. **Estado del problema** — qué sabemos, qué falta, qué pide el usuario y quién decide.
2. **Descomposición** — requisitos atómicos, superficies, actores, entrada, acción, resultado,
   error y dependencias.
3. **Alternativas** — al menos dos opciones cuando haya una decisión real; conserva la opción
   descartada viable como `plan_b` con condición de activación.
4. **Evaluación** — rendimiento, mantenibilidad, seguridad, simplicidad, coste de preguntas y
   riesgo de omitir una superficie.
5. **Decisión** — tradeoff explícito, fuente (`usuario`, `artefacto`, `inferencia` o
   `COMMITTEE`) y confianza.
6. **Verificación** — evidencia actual, edge cases, contradicciones, alcance observado y lo que
   sigue `UNVERIFIED`.

## Guardas

- No conviertas una inferencia, consenso, nombre de test o ausencia de salida en evidencia
  directa.
- Si falta un dato que cambia intención, UX, API, permisos, datos, seguridad o aceptación,
  pregunta en modo normal y pausa. En `COMMITTEE`, registra el supuesto sin venderlo como
  hecho.
- Todo requisito user-facing se expresa como recorrido: `actor → entrada → acción → resultado`
  más error/estado cuando aplique. Un backend funcional no cubre una entrada UI omitida.
- `LIGHT` solo vale para texto disponible, local, síncrono, determinista y sin IO, UI, actor,
  estado, seguridad, interacción ni duda. En otro caso usa `FULL`.
- En análisis-only no afirmes cambios ni runtime. En una UI inaccesible no afirmes presencia ni
  ausencia de un botón.
- Si el ledger o handoff llega incompleto, stale o contradictorio, detén el cierre y marca
  `BLOCKED`/`HOLD`; no rellenes huecos por memoria.

## Sesgos a evitar

- **Anclaje**: no te cases con la primera solución.
- **Disponibilidad**: no elijas lo primero que recuerdes.
- **Sobrecorrección**: no añadas agentes, fases o checks sin cobertura nueva.
- **Consenso falso**: dos agentes de acuerdo no son una prueba.
- **Contrato equivocado**: comprobar que funciona no valida que era lo que el usuario quería.
- **Cierre ritual**: no confundas ledger coherente con funcionalidad verificada.
