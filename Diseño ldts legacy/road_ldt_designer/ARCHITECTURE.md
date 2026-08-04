# Arquitectura inicial

## Flujo

```text
Geometría de calle + r-table
        │
Disposición de luminarias, soportes y brazos
        │
Clase luminotécnica + límites de aceras e intrusión
        │
Generador de candidatos I(C,γ)
        │
Cálculo punto a punto EN 13201-3
        │
Uo · Ul · fTI · SR/EIR/REI
        │
Optimización multiobjetivo
        │
LDT + informe + trazabilidad
```

## Separación de responsabilidades

### 1. Dominio de proyecto

`road_ldt/domain.py` contiene únicamente datos y validaciones:

- sección completa de calle y anchura individual de carriles;
- aceras, medianas, bandas laterales y edificios colindantes;
- tipo de superficie y `r-table`;
- posiciones de soportes, brazos, altura, orientación, inclinación y separación;
- objetivos mínimos/máximos de calidad;
- perfil normativo usado para interpretar el resultado.

### 2. Núcleo fotométrico independiente

El proyecto tendrá su propio parser EULUMDAT, geometría, r-tables y calculador
viario. Si se considera útil una implementación de otro proyecto, se copiará
y revisará dentro de esta carpeta. No habrá imports, rutas relativas ni
dependencias de ejecución hacia el proyecto de túneles.

La fórmula base de luminancia será la de EN 13201-3:

```text
L(P) = Σ [ I(C,γ) · fM · r(tan ε, β) / H² ]
```

Para iluminancia horizontal se usará el cálculo punto a punto del mismo
núcleo, manteniendo las convenciones de ángulos, observador y orientación.

### 3. Métricas

El contrato de resultados debe contener las dos familias siguientes:

| Campo | Dirección de cumplimiento | Uso |
|---|---:|---|
| `Uo` | mínimo | uniformidad global de luminancia |
| `Ul` | mínimo | uniformidad longitudinal |
| `TI` / `fTI` | máximo | deslumbramiento perturbador |
| `SR` | mínimo | compatibilidad con EN 13201-3:2003 |
| `EIR` / `REI` | mínimo | criterio equivalente usado en EN 13201-2:2015 |

`SR` no se debe presentar como el criterio actual de EN 13201-2:2015 sin
indicarlo: en la edición 2015 el parámetro de borde es EIR/REI. La aplicación
calculará ambos cuando la geometría permita comparar las bandas laterales.

### 4. Generación del LDT

El candidato fotométrico tendrá:

- malla de planos `C` y ángulos verticales `γ`;
- matriz de intensidades en `cd/klm`;
- código de simetría EULUMDAT;
- flujo de referencia y metadatos;
- límites de intensidad y reglas de suavizado.

El exportador escribirá un fichero ASCII EULUMDAT con intensidad en `cd/klm`,
flujo declarado y todos los campos necesarios para que pueda ser reimportado
por el parser existente.

### 5. Modelo geométrico de calle

La geometría no se limitará a un rectángulo de calzada. Debe representar:

- número y anchura individual de carriles;
- acera izquierda y derecha, con anchura, cota y superficie;
- medianas, aparcamientos, carriles bici y otras bandas laterales;
- fachadas o límites de parcela paralelos a la vía;
- edificios colindantes con retranqueo, altura y bandas de ventanas;
- zonas de evaluación vertical para intrusión luminosa.

Las luminarias se modelarán desde el soporte hasta el centro fotométrico,
incluyendo altura, saliente, longitud y dirección del brazo, orientación y
tilt. Las disposiciones iniciales serán unilateral, bilateral enfrentada,
bilateral tresbolillo y central doble.

### 6. Ingeniería inversa de lentes

Los parámetros de calidad de una instalación no determinan un único LDT. Por
eso el problema se tratará como una optimización inversa regularizada:

```text
requisitos viarios
      ↓
familia de I-tables candidatas
      ↓
restricciones de fabricabilidad y simetría
      ↓
evaluación EN 13201
      ↓
LDT objetivo para diseño óptico
```

La familia de candidatos estará controlada por variables como:

- ángulo de máximo longitudinal y transversal;
- anchura de haz y colas de distribución;
- corte hacia fachadas, edificios, cielo y zonas no útiles;
- asimetría lateral permitida por la sección transversal;
- simetría longitudinal obligatoria respecto al plano perpendicular a la vía;
- simetrías permitidas por la lente;
- flujo total, intensidad máxima y continuidad angular;
- límites de pendiente y suavizado de la matriz `I(C,γ)`.

El LDT generado será una especificación fotométrica objetivo para el diseño
de la lente. No se considerará una prueba de que la lente física ya existe:
después del diseño óptico se reimportará el LDT medido o simulado, se volverá
a calcular la instalación y se iterará sobre las diferencias.

### 7. Optimización

Se recomienda una estrategia por fases:

1. encontrar candidatos que cumplan la clase luminotécnica;
2. cumplir las iluminancias mínimas de aceras y bandas de uso;
3. respetar límites de intrusión en fachadas y ventanas;
4. minimizar flujo/potencia y emisiones fuera de la calle;
5. maximizar el margen mínimo de cumplimiento;
6. suavizar la matriz `I(C,γ)` y penalizar discontinuidades no fabricables;
7. exportar solo candidatos validados por una segunda lectura del LDT.

No se debe optimizar únicamente `Uo` y `Ul`: al escalar toda la intensidad
esas uniformidades permanecen casi constantes, mientras que `TI`, la
intrusión y los niveles absolutos sí cambian.

## Perfiles normativos

- `EN13201-2015`: perfil inicial de producción; usa `fTI` y EIR/REI.
- `EN13201-2003`: perfil de compatibilidad; permite reportar SR histórico.
- `prEN13201-2026`: reservado; no debe activarse como norma de proyecto hasta
  que el usuario confirme que desea trabajar con el texto publicado como
  proyecto y no con la edición vigente aplicable.

## Estado del núcleo

Ya están implementados:

- la malla geométrica 3D;
- la interpolación de la tabla `I(C,γ)`;
- la iluminancia directa sobre superficies horizontales y verticales;
- las tablas viarias R1-R4 con interpolación bilineal;
- un observador por carril, situado 60 m antes de la primera fila;
- la luminancia mantenida de calzada;
- `Lavg`, `Uo` y `Ul`, conservando el peor observador;
- simetrización y validación longitudinal de candidatos;
- repetición longitudinal de una celda fotométrica;
- `fTI` con magnitudes iniciales, posiciones longitudinales y peor observador;
- bandas de borde y cálculo de `EIR/REI`;
- cálculo separado de `SR` para compatibilidad histórica;
- evaluador unificado con fachadas, ventanas e intrusión opcionales;
- familia vial v2 con lóbulos longitudinales y transversales, continuidad en
  el nadir, semillas de ópticas reales y normalización fotométrica;
- lector y escritor EULUMDAT estándar con expansión de simetrías `Isym 0-4`;
- curvas polares y sólido 3D construidos desde el LDT final reimportado;
- importación de LDT físico de Photopia o laboratorio;
- comparación normalizada de forma, pico, anchuras, emisiones angulares y
  simetría;
- recálculo objetivo-físico sobre la misma vía y tabla de diferencias de
  calidad luminotécnica;
- mapa angular firmado del residual físico-objetivo;
- generación de un objetivo precompensado con ganancia ajustable, suavizado,
  simetrización y conservación del flujo para la siguiente iteración óptica;
- visor sincronizado 3D/2D con cortes `I(γ)` interpolados por plano `C`,
  comparación de simetría y superposición objetivo-físico-precompensado.

La opción `evaluate_intrusion` es `False` por defecto. Desactivarla significa
que no se construyen mallas de fachada o ventanas, no se calculan sus
iluminancias y sus límites no participan en el cumplimiento. Las bandas
laterales y `REI` se controlan con opciones independientes.

La búsqueda fotométrica usa una pirámide angular configurable:

| Etapa | Paso C | Paso γ | Uso |
|---|---:|---:|---|
| `coarse` | 10° | 5° | exploración global |
| `medium` | 5° | 2,5° | selección y refinamiento |
| `fine` | 2,5° | 1° | verificación de candidatos |
| `export` | 1° | 1° | LDT final |

La distribución se regenera desde sus parámetros en cada nivel. Esto evita
que los errores de una malla gruesa se propaguen por interpolación.

## Optimización disponible

La función objetivo, los límites de variables y el primer optimizador inverso
ya están implementados. Antes de aceptar un candidato final se exporta y se
vuelve a leer el LDT. La ordenación de candidatos es lexicográfica:
primero viabilidad, después máxima infracción normalizada y finalmente coste
total con regularización de intensidad máxima y suavidad.

El optimizador usa NumPy como acelerador y conserva el núcleo escalar como
referencia. Las pruebas comparan iluminancia, luminancia, uniformidades, `TI`,
`REI`, bandas e intrusión entre ambos motores.

## Próxima fase

- validar cuantitativamente contra casos de referencia externos EN 13201/CIE 140;
- convertir la biblioteca de ópticas SALVI en un banco versionado de regresión;
- incorporar configuración de proyecto serializable;
- añadir isolíneas y mapas explícitos de incumplimientos.
