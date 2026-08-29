# Luminaria Optimizer

Backend independiente para optimizar luminarias con módulos de LED LUXEON HL2X
3535. La primera fase calcula los puntos eléctricos y
térmicos, compone un LDT sintético a partir del LDT del grupo y prepara las
tablas de reflexión para el cálculo vial.

## Principios

- La variable de control es la corriente por LED de cada grupo.
- Los tres LED de un grupo están en serie, por lo que la corriente del grupo
  es la corriente de cada LED y su tensión es `3 * Vf`.
- La regulación permitida es de 0 a 2.000 mA en pasos de 50 mA.
- El LDT del grupo ya contiene los tres LED y la lente; no se vuelve a aplicar
  una eficiencia óptica sobre su flujo de referencia.
- Durante el cálculo vial se mantienen fuentes virtuales en la posición
  de cada luminaria. Cada fuente conserva el LDT base y su azimut de grupo y
  se escala con su propio flujo. No se regenera un LDT compuesto por cada
  combinación de corrientes.
- El modelo de flujo, `Vf`, temperatura y potencia sigue el acoplamiento
  iterativo empleado por los motores de SALVI.
- El modo modular permite configurar el número de canales; el modo fijo utiliza
  una única corriente global
  simultáneamente; el modo temporal del multiplexor queda explícito en la
  configuración y no se inventa un `duty-cycle`.
- Un LDT compuesto es una predicción calculada y no sustituye una medición de
  laboratorio.
- `edge_offset_m` es la distancia transversal entre el centro fotométrico y el
  borde de la calzada. Se aplica hacia fuera en ambos lados y no se suma al
  brazo.

## Ejecutar pruebas

Desde `luminaria_optimizer/backend`:

```text
python -m pytest
```

Con las dependencias instaladas, la API local se inicia con:

```text
python -m luminaire_optimizer
```

Endpoints iniciales:

- `GET /api/health`
- `POST /api/group/operating-point`
- `POST /api/luminaire/compose`
- `POST /api/road/calculate`
- `POST /api/optimize`
- `POST /api/optimizer/chat`

`/api/luminaire/compose` es una exportación opcional para documentar una
 solución. `/api/road/calculate` y `/api/optimize` calculan directamente la
 suma de las fuentes virtuales configuradas.

Ambos endpoints viales aceptan opcionalmente `reference_luminaire_ldt_base64`.
Cuando se proporciona, evalúan también ese LDT completo como una única fuente
con su flujo declarado y devuelven `reference_road` para comparar `Lavg`,
`Uo`, `Ul`, `TI` y `REI` con la solución calculada por grupos.

La API recibe los LDT y las tablas `.rtb` como Base64 para mantener el núcleo
sin rutas de disco ni base de datos.

El modo simétrico de la API empareja los grupos `G1/G8`, `G2/G7`, `G3/G6` y
`G4/G5` respecto al plano transversal `C=90°`, y simetriza el LDT base
promediándolo con su reflexión local. El modo
`photometry_symmetry="asymmetric"` conserva el LDT original para la fase
asimétrica posterior.

## Limitación normativa actual

La evaluación vial conserva `TI` como criterio bloqueante. El cálculo del
deslumbramiento debe validarse con un LDT que contenga la emisión necesaria
hacia el observador. El LDT de grupo disponible actualmente llega a
`gamma=90°`; con alturas inferiores a 1,5 m no debe declararse conformidad
normativa hasta confirmar la fotometría del hemisferio superior o definir el
procedimiento físico aplicable.

El paquete no depende de `luxStudio` ni de la aplicación de túneles.

## Modelos CAD

Los modelos nativos se mantienen en `modelos lentes/` en la raíz del proyecto.
Se admiten piezas `SLDPRT`, ensamblajes `SLDASM` y paquetes `ZIP` o `RAR` que
contengan el ensamblaje y sus piezas referenciadas. La aplicación abre el
documento nativo mediante SolidWorks y obtiene la teselación de sus caras en
memoria para el trazado de rayos; el usuario no tiene que exportar STEP.

Para habilitar la edición CAD y la lectura de paquetes RAR:

```text
python -m pip install -e ".[solidworks,geometry]"
```

## Ray file TM-25

El backend expone `parse_tm25()` para leer ray files binarios IES TM-25-13.
Los registros se abren como `numpy.memmap`, por lo que el procesamiento puede
hacerse por bloques sin cargar el fichero completo en memoria. El ray file
`LUXEON HL2Z_5000000Rays_IESTM25.tm25ray` corresponde a un LED HL2Z 4070
individual; no sustituye al LDT del grupo de tres LED y lente.

Para habilitar la geometría CAD nativa en otra instalación:

```text
python -m pip install -e ".[geometry]"
```

La secuencia `load_step_geometry()` → `trace_tm25()` → `rays_to_ldt()`
importa el ensamblaje, traza una muestra de los rayos por los tres LED y
genera una matriz LDT fina. El trazador conserva en los metadatos el flujo que
queda fuera de `gamma=0–90°`, ya que esa es la cobertura del LDT de referencia.
La geometría se tessela una vez y las intersecciones se resuelven con Embree;
la prueba de `1.000.000` de rayos por LED produjo `3.000.000` trayectorias en
`149 s` en el entorno de desarrollo.

La pantalla Modelo usa los endpoints CAD nativos mediante el modo
`Calcular desde la lente`: recibe el modelo y el TM-25, detecta sus parámetros,
permite modificarlos en la propia interfaz, calcula el LDT y carga el resultado
como LDT de grupo para la fase vial. La respuesta devuelve una muestra visual
de rayos transmitidos, no el millón completo. Cada trazado de una pieza conserva
una copia nativa con marca temporal en `modelos lentes/`; el original no se
sobrescribe. Los cambios de conversación o configuración no crean candidatos
nuevos. El endpoint STEP se conserva solo para importaciones externas.

La pantalla Modelo incluye también el diálogo `Copiloto óptico`, que usa el
trazado, las superficies y los parámetros CAD como contexto para discutir
estrategias antes de aplicarlas. Las propuestas requieren aprobación explícita;
la ejecución automática de barridos paramétricos y su cancelación quedan como
la siguiente ampliación del flujo.

La optimización vial usa por defecto corrientes independientes y conserva la
direccionalidad del LDT. El modo simétrico (`G1=G8`, `G2=G7`, `G3=G6`,
`G4=G5`) sigue disponible explícitamente para luminarias cuya fotometría real
lo justifique. El selector solo limita las corrientes; ninguno de los dos
modos busca, promedia ni simetriza el LDT. En ambos casos se valida `Lavg`,
temperatura, potencia, `TI` y `REI` con el cálculo completo.

En la convención vial, `C0/C180` son las direcciones longitudinales de la
calzada y `C90/C270` las transversales. Un LDT cuyo eje C termina en `C180` se
trata como direccional y no se cierra artificialmente hacia `C360/C0`.
El LDT de grupo se gira 90° en sentido horario al trasladarlo al marco de la
luminaria completa; después se conserva únicamente la emisión completa `C0–C180`.
Las luminarias del lado derecho se giran 180 grados para que `C90` siga
apuntando hacia la calzada; no se interpreta `C270` como el eje interior de
esa luminaria.
