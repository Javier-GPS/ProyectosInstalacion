# Luminaria Optimizer

Backend independiente para optimizar una luminaria de ocho grupos de tres
LED LUXEON HL2X 3535. La primera fase calcula los puntos eléctricos y
térmicos, compone un LDT sintético a partir del LDT del grupo y prepara las
tablas de reflexión para el cálculo vial.

## Principios

- La variable de control es la corriente por LED de cada grupo.
- Los tres LED de un grupo están en serie, por lo que la corriente del grupo
  es la corriente de cada LED y su tensión es `3 * Vf`.
- La regulación permitida es de 0 a 2.000 mA en pasos de 50 mA.
- El LDT del grupo ya contiene los tres LED y la lente; no se vuelve a aplicar
  una eficiencia óptica sobre su flujo de referencia.
- Durante el cálculo vial se mantienen ocho fuentes virtuales en la posición
  de cada luminaria. Cada fuente conserva el LDT base y su azimut de grupo y
  se escala con su propio flujo. No se regenera un LDT compuesto por cada
  combinación de corrientes.
- El modelo de flujo, `Vf`, temperatura y potencia sigue el acoplamiento
  iterativo empleado por los motores de SALVI.
- La primera versión supone que los ocho canales están activos
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

`/api/luminaire/compose` es una exportación opcional para documentar una
solución. `/api/road/calculate` y `/api/optimize` calculan directamente la
suma de las ocho fuentes virtuales.

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
