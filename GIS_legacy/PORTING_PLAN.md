# SALVI GIS — Guía funcional y plan de portado

> Documento de trabajo para trasladar la lógica útil de `GIS_legacy` a `GISvial`.
> No es una instrucción para copiar el monolito. Legacy sirve como referencia de
> comportamiento; GISvial es el destino técnico.
>
> Estado: `D0 — alcance y grupos definidos`  
> Fecha: 2026-07-26

---

## 1. Qué tiene que hacer el producto

SALVI GIS sirve para preparar y diseñar alumbrado público sobre espacios reales.
El recorrido esencial es:

```text
proyecto
  → zona
    → revisión de calles y datos disponibles
      → recorrido de trabajo entre punto A y punto B
        → tramos homogéneos y campos pendientes
          → selección/corrección de la red
        → posición de luminarias de diseño
          → validación, fotometría, inventario y exportación
```

El usuario debe poder:

1. **Seleccionar una parte de una calle entre dos puntos**, sin obligar a incluirla entera.
2. **Seleccionar áreas**, distinguiendo la envolvente de trabajo de los sectores
   superficiales que haya dentro.
3. **Añadir calles o elementos lineales manuales** cuando OSM no sea suficiente.
4. **Editar la red útil**: extender, dividir si procede, borrar o corregir un tramo,
   sin destruir la fuente OSM.
5. **Posicionar luminarias de diseño** individualmente o por reglas de tramo.
6. Seleccionar luminarias, editarlas por unidad o grupo y conservar sus cambios.
7. Llevar el resultado a validación/fotometría, inventario y exportación.

La aplicación no debe obligar a trabajar con una calle completa: el usuario marca un punto
inicial y otro final sobre la red y confirma el recorrido intermedio. La selección puede
cubrir parte de una calle, varios tramos, un parque u otro espacio público.

### 1.1 Glosario funcional

| Término | Significado de trabajo | Estado |
|---|---|---|
| Proyecto | Contenedor operativo de zonas y actuaciones | `CONFIRMADO` |
| Zona | Envolvente operativa o geográfica de consulta | `OBSERVADO`; no equivale automáticamente a un ámbito |
| Ámbito de actuación | Superficie concreta que se va a estudiar; puede cubrir parte de una calle | `CONFIRMADO` |
| Sector | Unidad superficial homogénea dentro de un ámbito: parque, plaza, aparcamiento, etc. | `CONFIRMADO` |
| Calle | Entidad lineal con uno o más tramos | `CONFIRMADO` |
| Tramo | Unidad lineal homogénea por características de vía | `CONFIRMADO` |
| Recorrido seleccionado | Cadena lineal conectada entre dos puntos elegidos y confirmada por el usuario; puede contener varios ways y tramos | `CONFIRMADO` |
| Luminaria de diseño | Punto propuesto o calculado para una actuación | `PROPUESTA` para el modelo final |
| Luminaria inventariada | Punto observado en campo; no es automáticamente una luminaria de diseño | `OBSERVADO` |
| OSM/Legacy | Fuente externa o histórica de lectura | `OBSERVADO` |

No se deben mezclar `zona`, `ámbito` y `sector` por comodidad de interfaz. Si el
producto decide que dos son la misma entidad, se documentará antes de cambiar el
modelo.

### 1.2 Política de datos físicos

Los atributos físicos se aceptan únicamente cuando proceden de una fuente explícita o de una
entrada del usuario. **No se inventan ni se rellenan con valores medios.**

Por cada tramo del recorrido se intentan obtener, como mínimo:

- ancho, material/superficie y número de carriles de la calzada;
- mediana, aparcamiento y carril bici cuando existan;
- acera izquierda y derecha: existencia, ancho y material;
- geometría, longitud y tipo de vía.

Reglas:

- un tag OSM ausente produce `null`, no un valor por defecto;
- conocer que existe una acera no permite inventar su ancho o material;
- la longitud puede derivarse de la geometría y se etiqueta como `derived`;
- cada campo conserva `source` (`OSM`, `manual`, `derived`) y estado (`known`, `missing`,
  `conflict`);
- el usuario puede guardar el recorrido con campos pendientes;
- un cálculo o generación que necesite un campo ausente se bloquea y muestra qué debe rellenar.

---

## 2. Regla de portado

### Sí portar

- El comportamiento útil que el usuario pueda observar y aceptar.
- Búsqueda y límites administrativos.
- Lectura, clasificación y actualización controlada de OSM.
- Selección por mapa/lista, filtros y visibilidad.
- Dibujo de zonas/ámbitos y creación de corredores cuando aporten valor.
- Correcciones manuales de la red.
- Colocación, selección y edición de luminarias de diseño.
- Estados de carga, error, reintento, cancelación y confirmación.
- Procedencia, identidad, revisión y trazabilidad.

### No copiar

- `api_server.py` ni sus handlers SQLite.
- Estado global de `SALVI GIS.html`.
- Escrituras directas desde JavaScript.
- Overpass llamado desde el navegador.
- Identidades basadas solo en nombre, índice o posición aproximada.
- Escritura simultánea en Legacy y GISvial.
- Datos de inventario de campo mezclados con luminarias diseñadas.
- Bugs o decisiones antiguas solo porque existan en Legacy.

La implementación nueva debe seguir siendo:

```text
React → API FastAPI → servicio de dominio → PostgreSQL
                         ↑
                    adaptador OSM/Legacy
```

El adaptador será de solo lectura al principio. GISvial tendrá un único propietario de
las escrituras nuevas.

---

## 3. Qué existe y qué falta ahora

Esta tabla evita releer el código completo. `OBSERVADO` describe código localizado; no
certifica por sí solo un recorrido completo de usuario.

| Capacidad | Legacy | GISvial actual | Portado pendiente |
|---|---|---|---|
| Proyecto/zona | Búsqueda, selección, renombrado, traslado y borrado | CRUD básico y wizard | Filtrado por proyecto, edición, límites y dibujo |
| Límite de zona | Nominatim, relación OSM, polígono y bbox fallback | Centro/bbox; el polígono no se conserva siempre | Contrato espacial y polygon-first |
| Carga OSM | Filtro de carreteras, túneles, 3 mirrors, caché y refresh | Endpoint servidor, validación, clipping bbox y carga si falta | Polígono, relación, filtros y actualización explícita |
| Calle/tramo | Ways, nombres, tipo, ancho, carriles, superficie, acera y túnel | `planning-inventory` agrupa targets y calcula longitudes | Identidad estable, selección directa y edición de red |
| Selección viaria | Lista, visibilidad, clic y herramientas de edición | Lista de planificación y visibilidad de mapa | Selección de calle/tramo sin confundir `target_ref` con ID permanente |
| Áreas/sectores | Zonas, polígonos y corredores | Zonas con `bounds_polygon` | Separar ámbito y sector; selección y cobertura parcial |
| Añadir/corregir calles | Clic, lazo, extender, borrar, editar ancho y deshacer | No hay entidad manual equivalente completa | Overlay local, validación y undo seguro |
| Luminarias de diseño | Colocación automática/manual, selección, edición individual/grupo | Modelo/API `GisLuminaire`; UI parcial | Posicionar y editar con asociación trazable |
| Inventario de campo | Importación y capa separada | `GisInventoryLuminaire` y endpoints | Mantenerlo separado; portar flujo después |
| Fotometría/exportación | Plantilla, importación, cumplimiento y DXF | Parte de API/UI existente | Revisar después de estabilizar tramos y luminarias |

### 3.1 Fuentes actuales

| Fuente | Datos | Uso inicial |
|---|---|---|
| SQLite Legacy | zonas, `zone_osm_data`, ways, luminarias e inventario | Referencia/muestras; no doble escritura |
| OSM/Overpass | red viaria y límites externos | Lectura mediante backend y caché declarada |
| `gis_zones` | proyectos, zonas, bbox, polígonos y relación OSM | Fuente GISvial de zonas |
| `gis_zone_osm_data` | caché OSM normalizada | Fuente de lectura de planificación |
| `gis_planning_drafts` | parámetros de planificación | Borrador, no geometría base |
| `gis_luminaires` | luminarias diseñadas | Propietario GISvial de diseño |
| `gis_inventory_luminaires` | luminarias observadas/importadas | Inventario separado |

`planning-inventory` es una proyección de lectura de la red OSM y sus snapshots. No es la
autoridad de las luminarias diseñadas, no sustituye al inventario de campo y no convierte
`target_ref` en una identidad permanente.

---

## 4. Riesgos espaciales que no se pueden ocultar

Hay datos con contratos distintos. No se hará una conversión global a ciegas.

- Legacy guarda el bbox como `sur,oeste,norte,este`.
- Algunas zonas nuevas de GISvial usan `sur,norte,oeste,este`.
- Legacy guarda polígonos como `[lat,lon]`.
- GeoJSON/MapLibre necesita `[lon,lat]`.
- El migrador actual copia bbox y polígonos sin conocer su procedencia.
- `target_ref` del inventario de planificación depende de snapshot/`source_index`;
  sirve para resolver una lectura, no como identidad de negocio permanente.

### Contrato propuesto

`PROPUESTA`, pendiente de validación antes de migrar datos:

1. Usar campos espaciales nombrados o un objeto, no una cadena ambigua.
2. Adoptar GeoJSON `[lon,lat]` para polígonos y geometrías que lleguen a MapLibre.
3. Conservar formato y valor original junto a `source`/`source_ref` durante la transición.
4. Declarar CRS, unidades, precisión, tolerancia y política de geometría inválida.
5. Resolver por procedencia antes de convertir; una fila ambigua queda en revisión.
6. Guardar un `snapshot_ref` (hash/revisión) de la red cuando una selección o luminaria
   dependa de ella.

PostGIS no es requisito del primer grupo. Se valorará solo para intersección, cobertura,
proximidad o recorte cuando la representación actual no sea suficiente.

El normalizador de transición deberá devolver siempre, aunque el almacenamiento físico cambie:

```text
{kind, canonical_id?, source, source_ref, snapshot_ref, geometry, crs,
 units, status, diagnostics}
```

`snapshot_ref` es el nombre canónico en este documento. “Snapshot” sin sufijo solo describe
el concepto en texto; no es otro campo.

Las fixtures espaciales se validan contra este DTO: coordenadas válidas conservan su orden y
CRS; coordenadas ambiguas o geometrías inválidas devuelven `status=ambiguous|invalid` y no se
usan para escribir.

### 4.1 Identidad del recorrido de trabajo

`PROPUESTA` mínima para persistir una selección A→B sin convertir OSM en autoridad de
escritura:

```text
work_scope_id
project_id, zone_id, ambit_id?
revision, status: draft|active|stale|archived
source_snapshot_ref
members[]: {
  work_segment_id,
  source_kind, source_ref, source_part,
  from_measure, to_measure, direction,
  source_geometry_hash,
  geometry,
  attributes_base, attributes_manual
}
```

- `source_ref` identifica el way/elemento fuente; `source_part` distingue piezas recortadas.
- `from_measure` y `to_measure` son fracciones finitas `[0,1]` medidas en el orden de
  coordenadas de la geometría fuente completa identificada por `source_geometry_hash` dentro
  de `source_snapshot_ref`.
- `direction` (`1|-1`) conserva el sentido de recorrido; los valores se normalizan a nueve
  decimales para comparar reintentos.
- `geometry` contiene únicamente el recorte efectivo entre las medidas, orientado según
  `direction`; no sustituye ni duplica la geometría fuente completa.
- `work_scope_id` y `work_segment_id` son IDs locales duraderos.
- Los members ordenados forman la identidad del recorrido. El nombre de calle es solo una
  etiqueta y nunca decide la continuidad.
- A=B se rechaza. Si A/B están en un bucle, rotonda o segmento con dos recorridos posibles,
  se previsualizan alternativas.
- En calles sin nombre, nombres duplicados/cambiados, calzadas separadas o cambios de tipo,
  cada continuación dudosa requiere confirmación o waypoint. No se enlaza automáticamente.
- Vincular opcionalmente el recorrido a un ámbito no crea ni modifica ese ámbito o sus sectores.

### 4.2 Capas y actualización OSM

Cada atributo efectivo sigue esta precedencia:

```text
manual → fuente OSM explícita → missing
```

No existe capa `estimated`. Al actualizar OSM:

1. se crea un nuevo `source_snapshot_ref`;
2. se intenta reconciliar cada member por `source_ref`, `source_part` y medidas;
3. se conservan todos los valores manuales;
4. si cambia el valor OSM bajo un manual, este prevalece pero se marca `source_changed`;
5. si cambia o desaparece la geometría y no puede reconciliarse con seguridad, el recorrido
   queda `stale` y requiere revisión; no se mueve ni se borra silenciosamente;
6. aceptar la reconciliación crea una revisión nueva del recorrido.

`source_changed` es un diagnóstico por campo (`unchanged|changed|removed`), no un estado del
recorrido. Un valor manual sigue `known`; un valor OSM cambiado sin override pasa a `conflict`
hasta revisión. El usuario puede ejecutar `clear_override`: se registra la operación y el campo
vuelve al valor OSM explícito o a `missing`.

La reconciliación de geometría solo reproyecta A/B si conserva `source_ref`, topología, orden y
queda dentro de una tolerancia declarada para el grupo. La tolerancia numérica debe fijarse antes
de implementar G3; sin ella, el recorrido queda `stale`.

### 4.3 Autoridad, permisos y escritura

| Operación | Lectura | Puede escribir | Regla |
|---|---|---|---|
| Datos Legacy/OSM | adaptador/cache | nadie desde GISvial | solo lectura al principio |
| Zonas del proyecto | usuario autenticado autorizado | servicio GISvial | comprobar proyecto/zona |
| Red local | usuario autorizado | servicio GISvial | no modifica `gis_zone_osm_data` |
| Luminaria de diseño | usuario autorizado | servicio GISvial | escribe `gis_luminaires` |
| Inventario de campo | usuario autorizado | flujo de inventario | separado de diseño |

La autenticación OIDC observada no demuestra por sí sola autorización por proyecto o zona.
Antes de una escritura se debe comprobar `401`, `403`, sesión caducada, coherencia entre
`project_id` y `zone_id`, concurrencia, auditoría y reintento. Si esa evidencia no existe,
el grupo se queda en `dry-run`/staging.

Capacidades mínimas propuestas: `project.read` para revisar la red y `road_scope.write` para
confirmar/modificar recorridos. El actor debe ser administrador o miembro autorizado del
proyecto; `zone.project_id`, `work_scope.project_id` y cualquier `ambit_id` deben coincidir.
Una referencia cruzada a otro proyecto se rechaza con `403`. Como el modelo actual no demuestra
membresía por proyecto, G3 persistente queda bloqueado hasta implementarla o declarar
explícitamente un despliegue solo para administradores.

La primera confirmación usa creación condicional `If-None-Match: *` más `operation_id`; devuelve
`ETag` de revisión 1. Modificar, reconciliar o archivar usa `If-Match` sobre el `ETag` de revisión
y aporta el `source_snapshot_ref` observado. La transacción vuelve a comprobar ambos: un recurso
ya creado o revisión obsoleta devuelve `412`; un snapshot fuente distinto devuelve `409`.
Edición manual y refresh OSM concurrentes nunca usan last-write-wins. Repetir el mismo
`operation_id` con el mismo payload devuelve el resultado anterior; con payload distinto se rechaza.

---

## 5. Grupos de migración

Cada grupo debe ser pequeño y vertical: actor → entrada → acción → resultado → error.
No se pasa al siguiente por intuición: se revisan diff, pruebas y recorrido observable.

### D0 — Este documento y matriz de paridad

**No modifica datos ni aplicación.**

Entrega:

- alcance y glosario;
- tabla Legacy/GISvial;
- contratos espaciales y de identidad pendientes;
- propietario de lectura/escritura;
- criterios de aceptación del siguiente grupo;
- referencias de código para leer solo lo necesario.

Salida: se puede elegir un caso real pequeño sin volver a leer todo `SALVI GIS.html`.

### G1 — Contexto de zona y área, solo lectura

Objetivo: seleccionar proyecto, zona y área de trabajo sin crear todavía entidades nuevas.

Incluye:

- filtrar zonas por proyecto;
- mostrar límite, centro, fuente y estado de datos;
- distinguir zona de ámbito/sector;
- consultar o seleccionar una zona con estados vacío/error/reintento;
- no convertir datos espaciales ambiguos.

No incluye: migración global, edición de polígonos ni creación de sectores.

Aceptación: al cambiar de proyecto solo aparecen sus zonas; seleccionar una zona centra y
resalta su contexto sin modificar datos.

### G2 — Red OSM y lectura de calles/tramos

Objetivo: que una zona tenga una red viaria fiable y legible.

Porta de Legacy:

- límite administrativo antes del bbox cuando exista;
- `osm_relation` y recuperación de polígono;
- allowlist de tipos de vía y túneles;
- mirrors, timeout, reintento y mensajes;
- caché existente frente a actualización explícita;
- ancho, carriles, superficie, acera, túnel y longitud.

La normalización no usa los anchos por defecto de Legacy como datos reales. Si OSM no aporta
un atributo físico, se conserva `null/missing` hasta que lo complete el usuario.

Reutiliza del actual, comprobándolo en cada grupo: backend, validación `remark`, clipping
geométrico, lock de proceso, hash/`snapshot_ref`, ETag y estados de `StepVias`. Son piezas
`OBSERVADAS` o `PARCIALES`, no una certificación de paridad completa.

Aceptación: cargar, actualizar, fallar y reintentar no pierde una caché válida; el usuario
ve tipo, nombre, tramo, longitud, geometría, atributos conocidos, campos pendientes y
procedencia. Ningún dato físico ausente aparece estimado.

### G3 — Seleccionar calles y tramos

Estado parcial (2026-07-26): GISvial ya permite dibujar un `Polygon` manual subordinado al
límite real de la zona, marcar A/B sobre targets del snapshot y guardar por zona el camino más
corto no dirigido dentro del área. El backend reconstruye A/B, recorta aristas, calcula Dijkstra,
persiste con CAS/ETag y marca la ruta `stale` al cambiar inventario o límite. La topología actual
se basa en coordenadas exactas porque el inventario todavía no conserva IDs de nodo, capas ni
sentidos OSM; por eso este slice no cierra aún la gestión de alternativas, auditoría/archivo,
linaje, permisos por proyecto ni reconciliación automática.

Objetivo: seleccionar un recorrido concreto entre dos puntos de una calle, sin inventar
identidad ni obligar a incluir la calle completa.

Primera versión: el usuario marca punto A y punto B sobre elementos de un `snapshot_ref`
conocido; la aplicación previsualiza el recorrido conectado y el usuario lo confirma. No se
crea una tabla universal de selección.

Reglas:

- `calle` y `tramo` se muestran separados;
- A y B se proyectan sobre la geometría fuente y conservan su referencia/posición;
- el recorrido puede cortar un way o atravesar varios ways/tramos de la misma calle;
- si hay ramificaciones o más de un camino válido, no se elige silenciosamente: se muestran
  alternativas o se pide un punto intermedio;
- un tramo sin geometría no se selecciona silenciosamente;
- `target_ref` se resuelve dentro de su `snapshot_ref`;
- nombre, índice o geometría no son identidad por sí solos;
- el recorrido confirmado se guarda como conjunto de trabajo del proyecto/zona;
- puede vincularse a un ámbito existente, pero nunca crea uno implícitamente;
- confirmar, sustituir, archivar o borrar el recorrido pasa por W0;
- cada tramo conserva sus atributos físicos conocidos y los ausentes quedan `null/missing`;
- cambios manuales posteriores no se sobrescriben al actualizar OSM.

Ciclo de vida:

```text
draft → active → stale → active
  └──────→ archived ←────┘
```

- `draft`: previsualización editable, no usable para cálculos.
- `active`: revisión confirmada.
- `stale`: conserva geometría/revisión anterior para inspección, pero bloquea colocar por regla,
  recalcular, dividir o exportar como vigente; permite comparar, reconciliar o archivar.
- `archived`: tombstone visible en auditoría; no borrado físico ordinario.
- Sustituir crea una revisión nueva conservando los mismos IDs cuando el member sobrevive; una
  división conserva linaje padre→hijos y da nuevos `work_segment_id` a los hijos.

Aceptación:

1. A y B dentro de una calle producen una previsualización recortada punto a punto.
2. Confirmar persiste el recorrido y sus referencias; recargar recupera la misma selección.
3. Un cruce ambiguo pide decisión y no escoge una rama automáticamente.
4. Un tramo sin geometría o un snapshot obsoleto produce un estado explícito.
5. Los campos físicos ausentes permanecen vacíos y editables, sin estimaciones.
6. Excluir o dividir por homogeneidad no altera la geometría fuente OSM.
7. Actualizar OSM conserva valores manuales; cambios de fuente se marcan y geometría no
   reconciliable deja el recorrido `stale` hasta revisión.
8. Guardar un valor manual y recargar conserva valor, fuente y revisión.
9. Un cálculo que requiera un campo `missing|conflict` queda bloqueado e indica el campo.
10. Doble confirmación, conflicto o actor sin permiso no duplica ni modifica el recorrido.
11. Carga, cancelación, red caída, reintento, sesión caducada, sin ruta y snapshot obsoleto
    muestran estados distintos y descartan respuestas tardías.

Evidencia mínima de G3:

| Criterio | Fixture | Evidencia directa esperada |
|---|---|---|
| A/B parcial | way simple con A/B interiores | UI previsualiza recorte; API devuelve members/medidas |
| Medidas/sentido | A=B, orden directo/inverso y redondeo límite | A=B rechazado; recorte reconstruible con direction/hash |
| Rama/bucle | cruce y rotonda con dos caminos | UI pide alternativa; no hay escritura previa |
| Calzadas separadas | ways paralelos del mismo nombre | no salta de calzada sin confirmación/waypoint |
| Persistencia | recorrido confirmado | DB/API antes-después y recuperación tras recarga |
| Sin estimaciones | tags físicos incompletos | DTO contiene `missing`; formulario vacío |
| Override/refresco | manual + nuevo snapshot OSM | manual persiste; diagnóstico/conflicto visible |
| Quitar override | campo manual con OSM presente/ausente | auditoría conserva acción; vuelve a OSM o `missing` |
| Concurrencia | dos revisiones/refresh simultáneo | una escritura acepta y otra devuelve conflicto |
| Permisos | otro proyecto/sesión caducada | `403`/`401` y estado DB idéntico |
| Stale | source_ref eliminado o geometría irreconciliable | revisión anterior visible; acciones dependientes bloqueadas |
| Ciclo/linaje | archivar y dividir un member | tombstone recuperable; padre/hijos e IDs trazables |
| Async | respuesta vieja tras cambiar A/B o cancelar | respuesta tardía descartada; selección actual intacta |

### G4 — Seleccionar ámbitos y sectores

Objetivo: seleccionar espacios superficiales sin tratarlos como calles.

Incluye:

- selección de un ámbito;
- selección de un sector;
- selección múltiple si el caso lo necesita;
- bordes, solapes y cobertura parcial documentados;
- mapa y lista con tipo e identidad.

No crea relaciones persistentes por proximidad. Una calle que cruza un ámbito puede quedar
como cobertura derivada hasta que exista una decisión de dominio.

Aceptación: un ámbito que cubre media calle no convierte automáticamente la calle completa en
seleccionada ni crea un sector implícito.

### W0 — Escritura segura común

Es el gate previo a cualquier creación, edición, importación o cálculo que escriba resultados.
No es un framework genérico: es el mínimo que necesitan la confirmación persistente de G3,
G5, G6, G7 y G8.

Debe comprobar:

- actor autenticado y autorizado para el proyecto/zona;
- entrada y geometría válidas, con CRS declarado;
- `operation_id`/clave de idempotencia y revisión del recurso;
- transacción completa o cero cambios parciales;
- procedencia, `snapshot_ref` y actor en el resultado/auditoría;
- respuesta estable para `401`, `403`, conflicto, duplicado y error de validación.

Aceptación: repetir una petición válida produce una única operación; una petición inválida,
no autorizada o obsoleta no cambia la base de datos.

### G5 — Crear una calle o elemento lineal local

Objetivo: suplir OSM con una entidad de planificación local. La primera entrega crea un
único elemento; no resuelve todavía toda la edición Legacy.

Porta la intención de añadir una calle, pero no sus globals ni su escritura.

Reglas:

- nunca modifica OSM, SQLite Legacy ni la caché base OSM;
- muestra geometría y atributos antes de confirmar;
- usa W0 y deja procedencia `manual` + `snapshot_ref` de contexto;
- devuelve un ID local estable;
- si requiere tramos, los crea explícitamente o deja estado `pendiente`, nunca los inventa.

Aceptación:

1. Una geometría válida se previsualiza y, al confirmar, aparece tras recargar.
2. Geometría inválida, duplicada o fuera del ámbito se rechaza sin cambios parciales.
3. Reintentar la misma operación no duplica el elemento.
4. OSM/Legacy permanecen sin cambios.

### G6 — Corregir la red local

Segundo paso de edición, separado de crear una calle. Cada acción debe ser un comando
trazable y reversible:

- extender;
- corregir atributos/ancho;
- dividir solo con regla de linaje;
- borrar con confirmación;
- deshacer mediante una operación nueva.

Aceptación:

1. La corrección cambia solo el overlay/local, nunca la geometría fuente OSM.
2. Una división conserva padre, hijos y procedencia; si no puede, se rechaza.
3. Borrar requiere confirmación y deja historial suficiente para deshacer.
4. Fallar o repetir una acción no deja geometrías o relaciones a medias.

### G7 — Posicionar luminarias de diseño

Objetivo: crear una `GisLuminaire` colocada en una actuación.

No mezclar con `GisInventoryLuminaire`.

Recorrido:

```text
usuario selecciona un tramo/ámbito o inicia colocación
  → marca una posición o aplica una regla acordada
  → revisa atributos y previsualización
  → API valida actor, coordenadas, snapshot_ref y asociación
  → guarda una luminaria GISvial
  → refresca desde la autoridad
```

No se hace snap silencioso a la calle más cercana. Si la asociación no es segura, se pide
confirmación o se deja el punto sin asociación con estado visible.

Primera entrega: una luminaria individual. Quedan como subgrupos posteriores, no incluidos en
la primera aceptación de G7: generación por interdistancia/distribución, selección múltiple,
edición individual/grupal, arrastre y deshacer.

Aceptación:

1. Una posición válida crea exactamente una `GisLuminaire` recuperable tras recargar.
2. La clase no se mezcla con `GisInventoryLuminaire` ni con un target OSM.
3. Coordenada, `snapshot_ref`, actor y procedencia quedan trazables.
4. Posición inválida, duplicado, conflicto o asociación ambigua produce estado visible y cero
   cambios parciales.
5. No hay snap ni asociación silenciosa a la calle más cercana.

### G8 — Validación, fotometría, inventario y exportación

Solo después de que G3/G4/G7 tengan identidad y geometría estables:

- seleccionar parámetros UNE-EN 13201 vigentes;
- generar plantilla para Lux Studio;
- importar resultados y pintar cumplimiento;
- importar/editar inventario de campo sin mezclarlo con diseño;
- DXF, informes y exportaciones.

Aceptación:

- una plantilla conserva la identidad del tramo/luminaria y su `snapshot_ref`;
- un resultado importado se asocia al elemento correcto o queda en conflicto;
- el mapa distingue sin resultado, aprobado, no aprobado y dato inválido;
- inventario de campo sigue separado de luminarias de diseño;
- importación y cálculo usan W0 o un gate equivalente documentado con exactamente estas
  evidencias: permisos, idempotencia, conflicto, formato inválido y cero cambios parciales;
- no se declara cumplimiento normativo por tener una clase seleccionada: hace falta resultado
  fotométrico y evidencia del cálculo.

### G9 — Herramientas auxiliares

Árboles OSM, satélite, terreno, ayuda, IA y mejoras de estilo se portan aparte. No deben
bloquear el recorrido principal de calles, áreas y luminarias.

---

## 6. Reglas de cada grupo

Antes de editar código:

1. Leer solo los anclajes del grupo y el contrato actual.
2. Registrar entrada, salida, permisos, error y datos afectados.
3. Elegir una fixture real o reversible.
4. Decidir quién escribe; Legacy/OSM no reciben doble escritura.
5. Mantener un plan B de lectura si falla la escritura.

Durante la edición:

- cambio mínimo;
- no renombrar por gusto;
- no introducir tipos o tablas sin necesidad del grupo;
- no ocultar datos ambiguos;
- no borrar caché válida ante respuesta externa dudosa.

Para cualquier control visible se verifica por separado: presencia, visibilidad/habilitación,
activación, carga/cancelación, éxito, error y reintento. También se anota actor, viewport,
sesión caducada, contraste/no dependencia exclusiva del color y alternativa de teclado cuando
aplique. Un endpoint verde no demuestra que el botón exista ni que su resultado llegue al mapa.

Las fixtures mínimas de los grupos espaciales deben cubrir: bbox en ambos órdenes, polígono
`[lat,lon]` y GeoJSON `[lon,lat]`, geometría vacía/inválida, tramo sin nombre, nombres
duplicados, way multipartes, borde de ámbito y respuesta OSM con `remark`. Cada fixture debe
indicar fuente, snapshot y resultado esperado.

Antes de cerrar:

- build/typecheck;
- pruebas unitarias del contrato;
- recorrido API con datos reversibles;
- recorrido UI para cualquier botón/control;
- revisión del diff actual;
- estado explícito: verificado, fallido o no verificado.

---

## 7. Matriz de paridad por comportamiento

Se completa una fila por función, no una frase genérica de “paridad”.

| ID | Comportamiento Legacy | Entrada | Resultado esperado | Error/estado | Destino | Grupo | Estado |
|---|---|---|---|---|---|---|---|
| P-01 | Buscar zona y dibujar límite | texto/resultado Nominatim | zona con centro, bbox y polígono | sin resultado/error | StepZona/API | G1 | `PENDIENTE` |
| P-02 | Recuperar límite administrativo | zona/relation | polígono válido | fallback bbox/error | servicio OSM | G2 | `PENDIENTE` |
| P-03 | Cargar calles OSM | zona + fuente | snapshot de ways/tramos | timeout/remark/reintento | backend OSM | G2 | `PARCIAL` |
| P-04 | Mostrar tipo de vía | `snapshot_ref` | grupo visible/ocultable | sin geometría | StepVias/MapView | G2/G3 | `PARCIAL` |
| P-05 | Seleccionar recorrido viario | puntos A/B + `snapshot_ref` + Polygon | recorrido multi-target calculado y persistido | rama ambigua/sin geometría/stale | StepVias/MapView/road-scope API | G3 | `PARCIAL` |
| P-05a | Completar datos físicos | recorrido + atributos OSM/manuales | datos por tramo con procedencia; ausentes en `null` | campo pendiente/conflicto | StepVias/API | G2/G3 | `PENDIENTE` |
| P-06 | Seleccionar sector | clic/lista | sector resaltado | solape/borde | futura UI/API | G4 | `PENDIENTE` |
| P-06a | Seleccionar ámbito | clic/lista | ámbito resaltado y diferenciado del sector | borde/solape | futura UI/API | G4 | `PENDIENTE` |
| P-07 | Añadir calle manual | geometría + atributos | elemento local trazable | inválida/duplicada | GISvial | G5 | `PENDIENTE` |
| P-08 | Corregir red local | comando + revisión | overlay corregido y reversible | conflicto/reintento | GISvial | G6 | `PENDIENTE` |
| P-09 | Colocar luminaria | posición + atributos | `GisLuminaire` persistida | fuera/duplicada/`snapshot_ref` | StepLuminarias/API | G7 | `PARCIAL` |
| P-10 | Editar grupo de luminarias | selección + cambio | cambios solo de diseño | conflicto/reintento | GISvial | G7 | `PENDIENTE` |
| P-11 | Exportar/calcular | tramo/luminarias | plantilla/resultado trazable | formato/error | Lux Studio | G8 | `PARCIAL` |
| P-12 | Importar fotometría | fichero + `snapshot_ref` | resultado asociado o conflicto | formato/identidad | Lux Studio | G8 | `PENDIENTE` |
| P-13 | Importar inventario | fichero + zona | inventario de campo separado | fila inválida/duplicada | GISvial | G8 | `PENDIENTE` |

Estados usados:

- `OBSERVADO`: localizado en código, sin afirmar recorrido completo.
- `PARCIAL`: existe una parte en GISvial y falta cerrar el flujo.
- `PENDIENTE`: todavía no portado o sin contrato.
- `BLOQUEADO`: falta una decisión que cambia datos, permisos o semántica.
- `VERIFICADO`: solo tras evidencia directa del recorrido declarado.

---

## 8. Anclajes para no leer todo el código

### Legacy: `SALVI GIS.html`

| Tema | Anclas |
|---|---|
| Configuración viaria | `ROAD_CFG`, `LIGHTING_CLASS_MAP` |
| Carga inicial/proyectos | `loadZonesFromAPI`, `switchProject` |
| Selección de zona | `selectZone`, `showAllZones` |
| Creación por búsqueda | `nominatim`, `geojsonToLatLngs`, `newZone` |
| Dibujo/corredor | `startDraw`, `corridor`, `loadZoneOSMPoly` |
| Límites y OSM | `fetchAdminBoundary`, `buildOverpassQuery`, `loadZoneOSM` |
| Red en mapa | `renderZoneWays`, `_rebuildZoneLayers` |
| Edición viaria | `add`, `extend`, `delete`, `lasso`, `undo` cerca de los handlers de ways |
| Luminarias | `placeStreetLuminaires`, `selectLumIds`, `_lumFieldValue` |
| Persistencia | `saveOsmDataToDB`, `apiPost('/api/luminaires/bulk'`, `apiGet('/api/luminaires` |
| Fotometría/exportación | `exportPlantillaLuminotecnica`, `importPhotometricResults` |

### GISvial: leer solo el grupo correspondiente

| Tema | Ficheros |
|---|---|
| Zona/proyecto | `frontend/src/components/Wizard/StepProyecto.tsx`, `StepZona.tsx`, `WizardShell.tsx` |
| Red/planning | `frontend/src/components/Wizard/StepVias.tsx`, `store/slices/viasSlice.ts` |
| Mapa/capas | `frontend/src/components/Map/MapView.tsx`, `hooks/useMapLayer.ts` |
| OSM | `backend/app/services/overpass.py`, `routers/zones.py` |
| Inventario | `backend/app/services/planning.py`, `models/gis.py` |
| Luminarias | `frontend/src/components/Wizard/StepLuminarias.tsx`, `backend/app/routers/luminaires.py`, `schemas/luminaires.py` |
| API/estado | `frontend/src/lib/api.ts`, `store/useGisStore.ts`, `store/slices/` |
| Contratos | `backend/app/schemas/zones.py`, `backend/app/schemas/luminaires.py` |

---

## 9. Plan B y criterios de parada

- Si el contrato espacial no se puede resolver: seguir con lectura por referencia y no
  escribir geometrías.
- Si un `source_snapshot_ref` nuevo no permite reconciliar un recorrido A→B: conservar la
  revisión anterior, marcar `stale` y exigir revisión; nunca reproyectar o mover en silencio.
- Si una entidad Legacy es ambigua: conservarla con estado `ambigua`; no emparejar por nombre.
- Si no hay permisos o idempotencia demostrables: solo `dry-run`/staging.
- Si una calle manual no tiene modelo estable: crear primero un overlay local, no modificar
  `gis_zone_osm_data`.
- Si una luminaria no puede asociarse de forma segura: guardar punto pendiente o bloquear;
  nunca hacer snap silencioso.
- Si el mapa no se puede observar: no declarar paridad UI por tener un endpoint verde.
- Si falla un grupo: no activar el siguiente; conservar la caché y abrir un grupo correctivo.

No se hará una migración global de SQLite ni se marcará una capacidad como terminada por tener
solo un modelo, endpoint o test unitario.

---

## 10. Próximo grupo

**G1 — Contexto de zona y área, solo lectura.**

Antes de escribir código se revisarán únicamente:

1. `StepProyecto`, `StepZona`, `WizardShell` y el slice de zonas.
2. `GET /api/zones?project_id=...` y su respuesta.
3. Conversión de bbox/polígono de una muestra Legacy y una zona GISvial.
4. Selección, centrado, capa de límite y estados de error.

Resultado esperado: una zona/área elegida en el proyecto correcto, con su procedencia y
geometría tratadas explícitamente. No se toca todavía la edición de calles ni la colocación
de farolas.
