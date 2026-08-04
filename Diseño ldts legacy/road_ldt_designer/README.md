# SALVI Road LDT Designer

Aplicación para diseñar y exportar distribuciones fotométricas viarias en
formato EULUMDAT (`.ldt`) a partir de una geometría de vía, una disposición de
luminarias y unos objetivos de calidad.

## Objetivo del producto

El sistema deberá encontrar una distribución `I(C, γ)` que, al instalarse en
la disposición indicada, cumpla los objetivos de proyecto:

- `Uo` y `Ul` sobre luminancia de calzada;
- `TI` (`fTI`) como incremento de umbral;
- `SR` como compatibilidad histórica y `EIR/REI` para el perfil
  EN 13201-2:2015.

La geometría incluirá la calle completa: carriles de anchura configurable,
aceras, bandas laterales, edificios colindantes y límites de intrusión
luminosa. Se admitirán disposiciones unilateral, bilateral enfrentada,
bilateral tresbolillo y central doble, con brazos y salientes parametrizables.

La salida no será solamente un número de flujo: incluirá el LDT generado,
los parámetros fotométricos, la malla de cálculo, las hipótesis normativas y
un informe de cumplimiento.

## Estado actual

Esta carpeta contiene el contrato de dominio, el escritor EULUMDAT, el
generador de mallas 3D de calle, el cálculo de iluminancia directa sobre
calzadas, aceras, fachadas y ventanas, las tablas R1-R4 y el primer núcleo de
luminancia de calzada.

Ya se calculan `Lavg`, `Uo` y `Ul` para un observador situado en el eje de cada
carril. También están implementados `fTI`, `EIR/REI` y el `SR` histórico. Los
resultados operativos conservan el peor observador o borde según corresponda.

El espacio de diseño exige simetría longitudinal respecto al plano vertical
perpendicular a la carretera. Por ello se calcula un único sentido de
observación; no existe una dirección configurable por carril. La instalación
se trata como un patrón longitudinal periódico.

El evaluador único permite activar o desactivar familias de cálculo. Fachadas,
ventanas e intrusión están desactivadas por defecto mediante
`EvaluationOptions(evaluate_intrusion=False)`. Cuando se activan, se generan
sus mallas, se calculan sus máximos y se incorporan sus límites al resultado de
cumplimiento. Cuando están desactivadas, esas mallas y comprobaciones no se
ejecutan.

El generador vial v2 combina lóbulos longitudinales, aporte transversal,
relleno próximo al nadir y una cresta gamma regulable con pendientes interior
y exterior independientes. Mantiene continuidad axial y simetría longitudinal,
usa semillas inspiradas en fotometrías viarias reales y normaliza cada
candidato a `1000 lm/klm`.
La resolución angular se aplica progresivamente:

- búsqueda gruesa: `C = 10°`, `γ = 5°`;
- refinamiento medio: `C = 5°`, `γ = 2,5°`;
- verificación fina: `C = 2,5°`, `γ = 1°`;
- exportación final: `C = 1°`, `γ = 1°`.

Los pasos son variables y las etapas pueden sustituirse para un proyecto
concreto. Cada etapa regenera la función fotométrica analítica y vuelve a
normalizarla; no interpola la matriz de la etapa anterior.

El motor aún no debe considerarse cerrado según EN 13201: falta consolidar las
reglas exactas de malla y validarlo con casos de referencia externos.

## Optimización disponible

El catálogo incluye las clases `M1` a `M6` de EN 13201-2:2015. El requisito
`REI` puede omitirse cuando las zonas adyacentes tienen requisitos propios.

La función objetivo utiliza infracciones normalizadas de `Lavg`, `Uo`, `Ul`,
`fTI` y `REI`, más las restricciones opcionales de bandas e intrusión. El
optimizador:

1. explora la familia en resolución gruesa;
2. conserva los mejores candidatos;
3. refina los parámetros en las mallas media y fina;
4. genera el LDT final a `1° × 1°`;
5. reimporta el LDT y repite la evaluación.

Durante la optimización se utiliza el backend NumPy. El backend escalar sigue
siendo la referencia y las pruebas exigen equivalencia numérica entre ambos.

El ejemplo M4 reproducible se ejecuta desde la raíz que contiene
`road_ldt_designer`:

```powershell
python -m road_ldt_designer.examples.optimize_m4_demo --output SALVI_M4_demo.ldt
```

Es una demostración de la cadena de cálculo, no una especificación de lente.

El motor de cálculo y el optimizador se construirán como un núcleo propio de
este proyecto. Cualquier código procedente de otros proyectos se copiará y se
adaptará aquí; nunca se importará el proyecto de túneles ni se compartirán
ficheros de ejecución entre ambos.

## Ejecutar las pruebas

Desde la raíz del proyecto:

```powershell
python -m pip install -r road_ldt_designer/requirements-dev.txt
python -m pytest road_ldt_designer/tests -q
```

La suite actual verifica dominio, exportación LDT, geometría 3D, interpolación
C-gamma, iluminancia directa, tablas R1-R4, observadores por carril,
luminancia de calzada, simetría longitudinal, repetición periódica, `fTI`,
`EIR/REI`, `SR`, evaluación opcional de intrusión y generación paramétrica.
También verifica la reimportación y comparación de un LDT físico contra el
objetivo sobre una misma instalación.

## Aplicación web

La primera interfaz está en `road_ldt_designer/web` y organiza el proyecto en
cinco fases: geometría, instalación, requisitos, optimización y resultados.
Permite editar carriles y aceras, escoger la disposición, configurar brazos,
activar opcionalmente la evaluación de edificios e intrusión y descargar el
LDT resultante. En resultados se puede cargar el LDT simulado por Photopia o
medido en laboratorio. La aplicación compara la forma normalizada de ambas
fotometrías, sus picos y anchuras, recalcula la vía y presenta las diferencias
de `Lavg`, `Uo`, `Ul`, `TI` y `REI`. El LDT físico dispone de su propio
visualizador 3D rotatorio. Además, se genera un mapa angular firmado del error
`I_físico - I_objetivo` y un siguiente LDT objetivo precompensado. La ganancia
de corrección es configurable; el residual se suaviza, se vuelve a imponer la
simetría longitudinal y se conserva el flujo integrado.

Junto al cuerpo fotométrico 3D se incluye un visor de cortes `I(γ)` con selector
continuo del plano `C`. El corte activo queda resaltado en el sólido 3D y puede
mostrarse en `cd/klm` o normalizado, para γ `0-90°` o `0-180°`. También permite
comparar el plano reflejado longitudinalmente y superponer objetivo, LDT físico
y objetivo precompensado.

La precompensación utiliza una hipótesis de error aditivo y sirve para dirigir
la siguiente iteración de la lente. No sustituye la simulación óptica: el nuevo
LDT de Photopia o de laboratorio debe reimportarse para comprobar la
convergencia real.

El lector acepta las simetrías EULUMDAT `Isym 0-4` y los campos textuales
opcionales vacíos que genera Photopia. La compatibilidad se ha comprobado con
los 27 ficheros LDT de referencia disponibles, sin introducir dependencias de
ejecución con otros proyectos.

En Windows, el arranque recomendado es hacer doble clic en
`arrancar_road_ldt.bat`, situado en la carpeta superior. El lanzador inicia un
único motor estable en `127.0.0.1:5050`, comprueba su estado y abre la
aplicación publicada. La ventana minimizada `SALVI Road LDT - Motor` debe
permanecer abierta mientras se realizan cálculos.

El motor HTTP se inicia desde la carpeta que contiene `road_ldt_designer`:

```powershell
python -m pip install -r road_ldt_designer/requirements.txt
python -m road_ldt_designer.api
```

Para iniciar el frontend:

```powershell
cd road_ldt_designer/web
Copy-Item .env.example .env.local
npm install
npm run dev
```

La variable `NEXT_PUBLIC_ENGINE_URL` conecta la interfaz con el motor, que por
defecto escucha en `http://127.0.0.1:5050`. Sin conexión la interfaz no calcula,
no declara cumplimiento y no genera descargas simuladas.

## Referencias de cálculo

La versión inicial se fija en EN 13201-2:2015 y EN 13201-3:2015, con
configuración versionada para poder incorporar la revisión futura sin cambiar
los resultados históricos. El formato LDT se tratará como EULUMDAT/CIE 121 y
la tabla de intensidades se expresará en coordenadas `C, γ`.
