# SALVI Road LDT Designer — instrucciones del proyecto

Este es un proyecto independiente del cálculo fotométrico de túneles.

## Regla de aislamiento

No modificar ni importar `CALCULO FOTOMETRICO SALVI`, sus módulos de túneles,
su `app.py` ni sus ficheros de ejecución. Si se necesita una implementación,
se copia y se adapta dentro de este proyecto, con sus propias pruebas.

## Objetivo técnico

Diseñar LDT nuevos mediante ingeniería inversa: a partir de la geometría de
una calle completa y de la disposición de luminarias, encontrar una distribución objetivo
`I(C,γ)` que cumpla Uo, Ul, TI y SR/EIR/REI, y que pueda entregarse al diseño
de lentes como especificación fotométrica.

La calle puede incluir varios carriles, aceras, medianas, carriles bici,
aparcamientos y edificios colindantes. Las disposiciones mínimas son
unilateral, bilateral enfrentada, bilateral tresbolillo y central doble; cada
luminaria puede incorporar brazo, saliente, orientación y tilt.

Un LDT objetivo debe incorporar restricciones de fabricabilidad, continuidad,
simetría, flujo, intensidad máxima y control de emisiones fuera de la calzada.
Los resultados deben distinguir siempre entre el LDT objetivo y el LDT físico
final obtenido por simulación o medición.

## Normativa versionada

La configuración inicial es EN 13201-2:2015 y EN 13201-3:2015. SR se conserva
como métrica histórica; el perfil 2015 utiliza EIR/REI para el borde.
