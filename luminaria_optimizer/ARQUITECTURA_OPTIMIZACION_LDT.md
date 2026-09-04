# Arquitectura de optimización basada en LDT

## 1. Decisión de proyecto

Se continuará sobre `luminaria_optimizer`. No se creará un proyecto nuevo.

El proyecto actual ya contiene las partes más específicas y difíciles de
reproducir:

- Apertura y reconstrucción de `SLDPRT` y `SLDASM` mediante SolidWorks.
- Teselación de superficies CAD.
- Trazado TM-25 con refracción, Fresnel y TIR.
- Intersección acelerada con Embree.
- Identificación de LED, caras y superficies.
- Generación de LDT a partir de rayos.
- Comunicación autónoma con SolidWorks.
- Interfaz web y copiloto local con Ollama.

El proyecto `Diseño ldts legacy` se utilizará como fuente de ideas y código
adaptable para:

- Generación analítica de LDT objetivo.
- Regularización de distribuciones fotométricas.
- Comparación entre LDT físico y LDT objetivo.
- Mapas residuales en coordenadas `C/Gamma`.
- Búsqueda por etapas y convergencia.

No se copiará el trazador legacy ni su interpretación de simetrías y ángulos
sin validarla contra las convenciones actuales.

## 2. Alcance

El objetivo de esta arquitectura es diseñar automáticamente una lente de grupo
de tres LED para aproximar un LDT de grupo objetivo.

El proceso tendrá tres niveles separados:

1. Generación del LDT objetivo de la luminaria.
2. Descomposición del LDT objetivo en contribuciones de grupo, dirección y flujo.
3. Optimización geométrica de la lente para reproducir el LDT de grupo.

La optimización de la calzada no se ejecutará dentro de cada ensayo CAD.

## 3. Definiciones

### 3.1 LDT objetivo de luminaria

Es la distribución fotométrica ideal de la luminaria completa necesaria para
cumplir los requisitos de una clase lumínica y una geometría vial determinada.

Puede no ser físicamente fabricable ni directamente generable por la lente. Se
considera una referencia matemática, no una medición ni una promesa de
fabricabilidad.

### 3.2 LDT de grupo

Es la distribución fotométrica de un grupo óptico de tres LED y su lente. En la
fase nueva será el objetivo geométrico que debe reproducir la lente.

### 3.3 Contribución direccional

Es una copia del LDT de grupo girada a una dirección `C` concreta y multiplicada
por un peso de flujo. El peso se convertirá posteriormente en una corriente de
grupo.

### 3.4 Residual fotométrico

Para cada celda angular:

```text
residual(C, gamma) = objetivo(C, gamma) - calculado(C, gamma)
```

El residual se analizará de forma absoluta y normalizada. La comparación de
forma no debe ocultar una pérdida de flujo total.

## 4. Flujo general

```text
Requisitos viales
      |
      v
LDT objetivo de luminaria
      |
      v
Descomposición en LDT de grupo, direcciones y pesos
      |
      v
LDT de grupo objetivo
      |
      v
Lente CAD + tres LED -> ray tracing -> LDT de grupo real
      |
      v
Residual por C/Gamma, LED, cara y rebote
      |
      v
Selección de la siguiente hipótesis y ensayo CAD
      |
      v
Convergencia y validación final
```

## 5. Fase A: generación del LDT objetivo de luminaria

### 5.1 Entradas

- Clase lumínica.
- Anchura de calzada y carriles.
- Altura, interdistancia, disposición y orientación.
- Tabla de reflexión.
- Objetivos mínimos de `Uo` y `Ul`.
- Límite de `TI`.
- Límites de `REI/SR` cuando proceda.
- Resolución angular del LDT.

`Lavg` no será la variable principal de forma. La luminancia absoluta se
normalizará y se escalará después mediante corriente.

### 5.2 Salida

La fase produce:

- `luminaire_target_ldt`.
- Métricas viales del objetivo.
- Resolución angular y convención de ejes.
- Parámetros de regularización.
- Evidencia de cumplimiento o incumplimiento de los objetivos.

### 5.3 Método inicial

Se adaptará la familia paramétrica de `Diseño ldts legacy` para generar
distribuciones suaves. La primera versión no usará una intensidad independiente
en cada celda, porque produciría soluciones con picos no fabricables.

El generador debe permitir, como mínimo:

- Posición del máximo en `C` y `Gamma`.
- Anchura longitudinal y transversal.
- Pendientes antes y después del máximo.
- Control de lóbulos y relleno próximo al nadir.
- Corte de emisión hacia gamma alto.
- Control de flujo total.

### 5.4 Función objetivo

La función objetivo del LDT de luminaria combinará:

```text
maximizar Uo y Ul
cumplir TI, REI/SR y límites normativos
penalizar rugosidad angular
penalizar picos aislados
penalizar emisión inútil hacia gamma alto o backlight
mantener una distribución suave y realizable
```

`Uo` y `Ul` son razones y no deben optimizarse sin conservar los niveles
absolutos y las restricciones normativas.

### 5.5 Coste de cálculo

Esta fase puede usar el evaluador vial existente y el generador analítico del
legacy. No debe abrir SolidWorks ni ejecutar ray tracing.

## 6. Fase B: descomposición del LDT objetivo

### 6.1 Modelo

La descomposición no será una división punto a punto. Las contribuciones de los
grupos se solapan angularmente.

El modelo será:

```text
T(C, gamma) ~= sum_j a_j * R(C_j, G(C, gamma))
```

Donde:

- `T` es el LDT objetivo de luminaria.
- `G` es el LDT de grupo objetivo.
- `R(C_j, G)` es el LDT de grupo girado a la dirección del grupo `j`.
- `a_j >= 0` es el peso de flujo del grupo `j`.

### 6.2 Resolución

Se utilizarán dos modos:

1. **Pesos con grupo fijo:** se conoce un LDT de grupo inicial y se resuelven
   los pesos `a_j` mediante mínimos cuadrados no negativos.
2. **Factorización conjunta:** se resuelven alternativamente `G` y `a_j`, con
   normalización de flujo y regularización de suavidad.

La factorización conjunta debe eliminar la ambigüedad de escala normalizando
`G`, por ejemplo a `1000 lm`.

### 6.3 Restricciones

- Pesos no negativos.
- Corrientes dentro de `0-2000 mA`.
- Pasos de corriente de `50 mA` cuando se conviertan a hardware.
- Límites eléctricos y térmicos.
- Conservación de flujo y potencia.
- Convención de eje C direccional `C0-C180`.
- No cerrar artificialmente un LDT direccional hacia `C360/C0`.

### 6.4 Salida

La fase produce:

- `group_target_ldt`.
- Peso o corriente relativa de cada dirección.
- LDT de luminaria reconstruido.
- Residual de descomposición.
- Contribución esperada de cada grupo.

La corriente se resolverá aquí o se dejará como vector de referencia. No se
volverá a optimizar dentro de cada ensayo geométrico.

## 7. Fase C: optimización de la lente

### 7.1 Sistema óptico

La lente contiene tres sistemas ópticos, cada uno asociado a un LED. La
identificación principal se hará por la cara de entrada:

```text
Sistema 1 -> cara de entrada 5
Sistema 2 -> cara de entrada 18
Sistema 3 -> cara de entrada 23
```

La numeración anterior es externa y humana, basada en SolidWorks. Internamente
se utilizarán índices cero cuando sea necesario.

Una rayectoria debe conservarse como:

```text
LED -> cara de entrada -> rebote 1 -> rebote 2 -> ... -> cara de salida
```

### 7.2 Comparación

Cada candidato CAD se evaluará contra `group_target_ldt`, no contra una nueva
simulación completa de calzada.

Se calcularán:

- Error absoluto y RMSE en `C/Gamma`.
- Error angular del eje principal.
- Desplazamiento del máximo.
- Anchura y dispersión del haz.
- Flujo transmitido.
- Eficiencia óptica.
- Flujo TIR.
- Flujo no interceptado.
- Residual por LED.
- Residual por cara de entrada.
- Residual por superficie de rebote.

La eficiencia objetivo inicial será aproximadamente `90 %`, con un umbral
configurable y documentado.

## 8. Trazabilidad completa de rayos

La muestra visual actual no es suficiente para aprender. El trazador debe
acumular durante todo el cálculo, sin guardar necesariamente cada coordenada
completa:

- LED de origen.
- Flujo del rayo.
- Estado óptico.
- Cara de entrada.
- Secuencia ordenada de caras de reflexión.
- Cara de salida.
- Dirección final.
- Coordenadas `C/Gamma`.
- Número de rebotes.
- TIR y transmisión.

Se conservarán dos niveles:

1. **Agregado completo:** histogramas y flujos por sistema, cara, rebote y
   celda angular.
2. **Muestra visual:** rutas completas limitadas para el visor y la inspección.

El agregado completo será la fuente de decisión del optimizador. La muestra
visual no debe utilizarse para estimar por sí sola el residual global.

## 9. Orden de corrección geométrica

La optimización se hará por capas de la trayectoria óptica:

1. Caras de entrada `5`, `18` y `23`.
2. Primeras caras de reflexión de cada sistema.
3. Segundas caras de reflexión.
4. Rebotes posteriores con contribución significativa.
5. Superficies de salida.

Al optimizar una capa:

- Los parámetros de capas anteriores quedan bloqueados o muy restringidos.
- Los otros sistemas quedan bloqueados.
- Solo se prueban parámetros asignados al sistema y a la capa actual.
- Una nueva topología debe volver a calcular las rutas desde cero.

No se debe asumir que una cara mantiene el mismo papel después de una
modificación geométrica. La ruta debe redescubrirse en cada candidato.

## 10. Hipótesis y tabla de ensayos

La IA no modificará directamente una cota por lenguaje libre. Generará una
hipótesis estructurada que el planificador validará.

Ejemplo:

```text
Hipótesis:
Reducir la cota de la parábola puede reducir la emisión por encima del corredor
objetivo del sistema de entrada 18.

Sistema: 2
Cara de entrada: 18
Capa: primer rebote
Parámetros: D2@CroquisParabola, D3@CroquisParabola
Ensayos: valores alrededor del estado actual
Restricciones: otros parámetros bloqueados, eficiencia >= 90 %
```

Cada ensayo tendrá:

- Identificador.
- Hipótesis de origen.
- Sistema y caras implicadas.
- Parámetros y valores propuestos.
- Estado base y candidato.
- Número de rayos utilizado.
- LDT generado.
- Residual angular.
- Flujo, TIR y eficiencia.
- Estado de SolidWorks.
- Archivo guardado.
- Resultado aceptado, rechazado o inválido.
- Motivo de la decisión.

## 11. Búsqueda no exhaustiva

El planificador utilizará optimización activa o `SMBO`:

1. Medir el estado base.
2. Ejecutar pocas muestras iniciales separadas dentro del rango seguro.
3. Estimar sensibilidad y construir un modelo sustituto.
4. Elegir el siguiente ensayo por mejora esperada o incertidumbre.
5. Reducir el rango alrededor de las mejores soluciones.
6. Detenerse cuando la mejora sea inferior al umbral durante varias pruebas.
7. Validar las mejores candidatas con más rayos.

No se probarán todas las combinaciones posibles.

Para evitar que el ruido del muestreo de rayos falsee la decisión:

- Se utilizarán semillas reproducibles.
- Las candidatas de una comparación compartirán, cuando sea posible, la misma
  muestra de rayos.
- Se usarán pocos rayos para explorar y más rayos para confirmar.
- Una mejora pequeña debe repetirse antes de aceptarse.

## 12. Presupuesto y convergencia

Cada ejecución autónoma tendrá un presupuesto explícito:

- Número máximo de parámetros activos.
- Número máximo de candidatos.
- Rayos de exploración.
- Rayos de validación.
- Tiempo máximo.
- Mejora mínima aceptable.
- Eficiencia mínima.

Una ejecución termina cuando:

- Se alcanza la mejora objetivo.
- No hay mejora suficiente en varias iteraciones.
- Se incumple una restricción dura.
- SolidWorks produce una geometría inválida.
- Se consume el presupuesto.

Si no hay mejora, se conserva la lente base y no se guarda una candidata.

## 13. Comunicación con SolidWorks

El acceso será un puente controlado, no acceso COM libre para la IA.

Operaciones permitidas:

1. Abrir una copia de trabajo.
2. Leer features y parámetros.
3. Aplicar valores de parámetros autorizados.
4. Reconstruir.
5. Obtener la geometría teselada.
6. Ejecutar ray tracing.
7. Evaluar el LDT.
8. Guardar una copia con referencia nueva.
9. Mantener o cerrar la sesión.

La IA no podrá:

- Inventar nombres de parámetros.
- Modificar parámetros fuera del grupo autorizado.
- Sobrescribir el original.
- Declarar una modificación sin confirmación del endpoint CAD.
- Ejecutar dos modificaciones simultáneas sobre la misma sesión.

El resultado debe informar siempre:

- Archivo realmente guardado.
- Parámetros realmente modificados.
- Valores antes y después.
- Estado de reconstrucción.
- Métricas del LDT base y candidato.
- Motivo de aceptación o rechazo.

## 14. Reutilización del código existente

### Se conserva

- `geometry.py`: geometría y metadatos CAD.
- `solidworks_session.py`: sesiones y edición SolidWorks.
- `optical.py`: trazado, refracción, TIR e intersecciones.
- `ray_photometry.py`: conversión de rayos a LDT.
- `ldt.py`: lectura, escritura y diagnóstico LDT.
- `road.py`: evaluación vial para generar y validar objetivos.
- `optimizer.py`: ideas de restricciones eléctricas y escalado final.
- Frontend React y visor 3D.
- Copiloto Ollama como generador de hipótesis.

### Se adapta

- Generador paramétrico de LDT del legacy.
- Validador angular del legacy.
- Regularización por suavidad y emisión inútil.
- Búsqueda por etapas del legacy.

### No se copia directamente

- Trazador de rayos legacy, porque no existe como tal.
- Simetrías `C -> 180-C` sin revisión.
- Convenciones beta de carretera sin validación.
- Optimización vial dentro de cada ensayo CAD.
- Escritura LDT con campos hardcodeados.

## 15. Módulos nuevos propuestos

```text
target_ldt.py
    Genera y optimiza el LDT objetivo de luminaria.

group_decomposition.py
    Descompone el objetivo en LDT de grupo, direcciones y pesos.

ldt_residual.py
    Compara LDT objetivo y LDT real en C/Gamma.

ray_attribution.py
    Agrega flujo y residual por LED, sistema, cara y rebote.

experiment_manager.py
    Registra hipótesis, ensayos, candidatas y convergencia.

cad_parameter_map.py
    Mantiene la asignación manual de parámetros a sistemas y capas.

active_search.py
    Selecciona ensayos mediante sensibilidad y modelo sustituto.
```

## 16. API prevista

Endpoints conceptuales:

```text
POST /api/target-luminaire/generate
POST /api/target-luminaire/decompose
POST /api/group/compare-target
POST /api/experiments/plan
POST /api/experiments/run
GET  /api/experiments/{experiment_id}
POST /api/experiments/{experiment_id}/cancel
```

El endpoint de ejecución recibirá una configuración validada, nunca una orden
CAD arbitraria generada directamente por texto.

## 17. Interfaz prevista

El frontend deberá rediseñarse para reflejar las fases fotométricas y no mezclar
el diseño de lente con el estudio vial. La navegación prevista será:

```text
01 Requisitos y LDT objetivo
02 Descomposición de luminaria
03 Diseño del LDT de grupo
04 Optimización autónoma de lente
05 Reutilización en estudios viales
```

La aplicación deberá mostrar separadamente:

- LDT objetivo de luminaria.
- LDT de luminaria reconstruido.
- LDT de grupo objetivo.
- LDT de grupo real.
- Corrientes derivadas de la descomposición.
- Residual angular.
- Sistema y cara que originan cada residual.
- Secuencia de rebotes.
- Tabla de ensayos.
- Mejor candidata y motivo de aceptación.
- Estado de SolidWorks y archivo guardado.

El copiloto podrá generar hipótesis y consultar el proceso, pero la decisión de
aceptación se basará en métricas calculadas por el backend.

### 17.1 Estado del frontend

El estado global debe distinguir estos artefactos:

- `LuminaireTargetLdt`: LDT objetivo ideal de la luminaria.
- `GroupDecomposition`: LDT de grupo, direcciones y pesos calculados.
- `GroupLdtArtifact`: LDT de grupo optimizado y su procedencia.
- `LensOptimizationRun`: historial de candidatas CAD y trazados.
- `RoadStudy`: configuración vial concreta y resultados eléctricos.

Un `RoadStudy` nunca debe modificar el `GroupLdtArtifact`. Solo puede probarlo,
escalarlo y resolver corrientes compatibles con la nueva instalación.

### 17.2 Pantalla de reutilización vial

Una vez conseguido el LDT de grupo optimizado, el usuario podrá:

1. Seleccionar un LDT de grupo guardado.
2. Elegir una nueva anchura de calle.
3. Cambiar interdistancia, altura, disposición, número de carriles y tabla R.
4. Mantener fija la forma fotométrica del LDT.
5. Resolver nuevas corrientes por dirección.
6. Evaluar `Lavg`, `Uo`, `Ul`, `TI`, `REI` y potencia.
7. Comparar el resultado con estudios anteriores.

Esta fase no debe abrir SolidWorks ni ejecutar ray tracing. El LDT de grupo ya
ha sido calculado y solo se reutiliza como fuente fotométrica escalable.

## 18. Reutilización del LDT de grupo en otras calles

### 18.1 Artefacto persistente

El LDT de grupo optimizado se guardará junto con metadatos suficientes para
reproducir su uso:

- Identificador y nombre del artefacto.
- Archivo LDT y contenido normalizado.
- Flujo de referencia.
- Corriente de referencia.
- CCT y CRI.
- Número de LED del grupo.
- Convención angular y rotación C.
- Resolución `C/Gamma`.
- Modelo CAD y versión de la lente de origen.
- Eficiencia óptica medida o calculada.
- LDT objetivo del que procede.
- Fecha y versión del trazador.
- Historial de ensayos que lo produjo.

El LDT debe conservarse normalizado para separar la forma fotométrica del flujo
absoluto. La corriente resolverá posteriormente el nivel de emisión necesario.

### 18.2 Nuevo estudio vial

El estudio de otra calle recibirá:

```text
GroupLdtArtifact + RoadScenario + límites eléctricos
```

El cálculo será:

```text
LDT de grupo fijo
        ↓
copias giradas a las direcciones configuradas
        ↓
escala por flujo y corriente de cada grupo
        ↓
cálculo vial
        ↓
resolución de corrientes
```

La forma angular no se reoptimiza. Solo se ajustan las escalas de cada grupo,
respetando corriente, temperatura, potencia y límites del driver.

### 18.3 Resultado de adaptación

Cada nuevo estudio debe informar:

- Si existe una solución de corrientes.
- Corriente por grupo y dirección.
- `Lavg`, `Uo`, `Ul`, `TI` y `REI`.
- Flujo y potencia total.
- Temperatura calculada.
- Margen hasta los límites eléctricos.
- Diferencia respecto al estudio anterior.
- Advertencias de incompatibilidad fotométrica.

Debe distinguirse entre:

- **Adaptable:** se cumplen los requisitos con cambios de corriente.
- **Adaptable con advertencias:** se cumplen los requisitos, pero con poco margen.
- **No adaptable:** la forma del LDT no permite cumplirlos aunque se cambie la
  corriente.

### 18.4 Límites de reutilización

El LDT de grupo puede reutilizarse en otra calle, pero no se debe afirmar que
será adecuado para cualquier geometría. Una nueva configuración puede requerir:

- Otra distribución angular.
- Otro LDT de grupo.
- Otra orientación o tilt.
- Más grupos o grupos con distintas corrientes.
- Una nueva optimización de lente.

El sistema debe detectar estos casos comparando el mejor resultado alcanzable
con los límites de corriente y declarando la causa del incumplimiento.

## 19. Plan de implementación

### Fase 1: contratos y datos

- Definir modelos de LDT objetivo, grupo, residual y ensayo.
- Definir la convención angular única.
- Definir el mapa manual de sistemas y parámetros.

### Fase 2: objetivo de luminaria

- Adaptar el generador paramétrico legacy.
- Evaluar `Uo`, `Ul`, `TI` y restricciones.
- Exportar y reimportar el LDT objetivo.

### Fase 3: descomposición

- Resolver pesos para un LDT de grupo fijo.
- Implementar factorización conjunta regularizada.
- Convertir pesos a corrientes de referencia.

### Fase 4: residual de grupo

- Separar LDT por LED y cara de entrada.
- Agregar histogramas por sistema y rebote.
- Comparar contra el LDT de grupo objetivo.

### Fase 5: ensayos autónomos

- Crear tabla de hipótesis y ensayos.
- Añadir mapa manual de parámetros.
- Implementar sensibilidad y búsqueda activa.
- Bloquear sistemas y capas no activas.

### Fase 6: SolidWorks y validación

- Ejecutar candidatas con presupuesto.
- Guardar copias versionadas.
- Validar con rayos altos.
- Ejecutar la calzada solo como validación final.

### Fase 7: frontend y reutilización

- Separar las pantallas de objetivo, grupo, lente y estudio vial.
- Crear el artefacto persistente `GroupLdtArtifact`.
- Permitir cargar un LDT de grupo optimizado en una nueva configuración vial.
- Resolver únicamente corrientes en el nuevo estudio.
- Comparar varios estudios con el mismo artefacto fotométrico.
- Mostrar claramente cuándo el problema requiere rediseñar la lente.

## 20. Criterios de aceptación

La primera versión se considerará válida cuando pueda:

1. Generar un LDT objetivo reproducible para una configuración vial.
2. Obtener un LDT de grupo objetivo y sus pesos direccionales.
3. Generar un LDT real del grupo desde el CAD.
4. Mostrar el residual en `C/Gamma`.
5. Atribuir el residual a las caras `5`, `18`, `23` y a los rebotes.
6. Crear una tabla de ensayos reproducible.
7. Ejecutar una candidata sin intervención entre ensayos.
8. Guardar una nueva referencia solo cuando exista mejora real.
9. No modificar corrientes durante la fase de optimización de lente.
10. Confirmar la mejora final con un trazado de validación.
11. Guardar un LDT de grupo optimizado con su procedencia completa.
12. Reutilizarlo en otra calle sin abrir SolidWorks ni ejecutar ray tracing.
13. Resolver corrientes nuevas para anchura, altura e interdistancia diferentes.
14. Declarar si la nueva instalación es adaptable, limitada o no adaptable.

## 21. Decisiones pendientes

- Resolución angular definitiva del LDT objetivo.
- Lista exacta de direcciones de los grupos.
- Umbral de eficiencia: `90 %` exacto o tolerancia alrededor de ese valor.
- Nombre interno de cada parámetro CAD asociado a los sistemas.
- Presupuesto inicial de candidatos y rayos.
- Umbral de convergencia.
- Si la factorización conjunta se activará desde el principio o después del modo
  de grupo fijo.
