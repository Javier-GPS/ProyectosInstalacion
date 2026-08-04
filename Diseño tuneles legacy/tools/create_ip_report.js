const fs = require("fs");
const path = require("path");
const {
  AlignmentType, BorderStyle, Document, ExternalHyperlink, Footer, Header, HeadingLevel,
  Packer, PageNumber, Paragraph, ShadingType, Table, TableCell, TableRow,
  TextRun, WidthType
} = require("docx");

const out = path.resolve(__dirname, "..", "Informe_PI_Patentes_Ecosistema_Digital_SALVI.docx");
const BLUE = "153A5B";
const BLUE2 = "1F4E78";
const LIGHT = "EAF1F8";
const PALE = "F5F8FC";
const GREEN = "E2F0D9";
const AMBER = "FFF2CC";
const RED = "FCE4D6";
const GRAY = "666666";
const pageWidth = 11906;
const margins = { top: 1000, right: 900, bottom: 900, left: 900 };

function run(text, opts = {}) {
  return new TextRun({ text, font: "Aptos", size: opts.size || 20, bold: opts.bold,
    color: opts.color, italics: opts.italics, break: opts.break, allCaps: opts.allCaps });
}

function p(text, opts = {}) {
  const children = Array.isArray(text) ? text : [run(text, opts)];
  return new Paragraph({ children, alignment: opts.alignment, spacing: {
    before: opts.before ?? 0, after: opts.after ?? 140, line: opts.line ?? 276
  }, border: opts.border, keepNext: opts.keepNext, pageBreakBefore: opts.pageBreakBefore });
}

function heading(text, level = 1, opts = {}) {
  return new Paragraph({ text, heading: level === 1 ? HeadingLevel.HEADING_1 : HeadingLevel.HEADING_2,
    spacing: { before: opts.before ?? (level === 1 ? 340 : 240), after: 130 }, keepNext: true,
    pageBreakBefore: opts.pageBreakBefore });
}

function bullet(text, level = 0) {
  return new Paragraph({ children: [run(text)], numbering: { reference: "bullets", level },
    spacing: { after: 80, line: 260 } });
}

function cell(text, width, opts = {}) {
  const children = Array.isArray(text) ? text : [p(text, { bold: opts.bold, color: opts.color, size: opts.size || 18, after: 0, line: 220 })];
  return new TableCell({ children, width: { size: width, type: WidthType.DXA },
    shading: opts.shading ? { type: ShadingType.CLEAR, color: opts.shading, fill: opts.shading } : undefined,
    verticalAlign: "center", margins: { top: 90, bottom: 90, left: 100, right: 100 } });
}

function table(headers, rows, widths) {
  const head = new TableRow({ children: headers.map((h, i) => cell(h, widths[i], { bold: true, color: "FFFFFF", shading: BLUE2, size: 17 })) });
  const body = rows.map((row, r) => new TableRow({ children: row.map((v, i) => cell(v, widths[i], { shading: r % 2 ? PALE : undefined, size: 17 })) }));
  return new Table({ rows: [head, ...body], width: { size: pageWidth - margins.left - margins.right, type: WidthType.DXA },
    columnWidths: widths, borders: { top: { style: BorderStyle.SINGLE, size: 4, color: "C7D5E5" }, bottom: { style: BorderStyle.SINGLE, size: 4, color: "C7D5E5" }, left: { style: BorderStyle.SINGLE, size: 4, color: "C7D5E5" }, right: { style: BorderStyle.SINGLE, size: 4, color: "C7D5E5" }, insideHorizontal: { style: BorderStyle.SINGLE, size: 3, color: "D9E2F3" }, insideVertical: { style: BorderStyle.SINGLE, size: 3, color: "D9E2F3" } } });
}

function link(label, url) {
  return new ExternalHyperlink({ link: url, children: [new TextRun({ text: label, style: "Hyperlink", font: "Aptos", size: 18 })] });
}

function platformSheet(s) {
  return [
    heading(`Ficha ${s.code}. ${s.name}`, 1, { pageBreakBefore: true }),
    p(s.description, { size: 18, after: 110, line: 250 }),
    p([run("Enfoque de protección. ", { bold: true, color: BLUE, size: 18 }), run(s.protection, { size: 18 })], { after: 90, line: 250 }),
    p([run("Qué debe demostrarse. ", { bold: true, color: BLUE, size: 18 }), run(s.evidence, { size: 18 })], { after: 130, line: 250 }),
    table(["Campo de la ficha de invención", "Contenido inicial para completar con el agente"], [
      ["Título de trabajo", s.title],
      ["Problema técnico", s.problem],
      ["Solución propuesta", s.solution],
      ["Efecto y evidencia", s.effect],
      ["Variantes a cubrir", s.variants],
      ["Inventores y fechas", "Identificar autores técnicos, aportación de cada uno, primera concepción, pruebas y cualquier divulgación o piloto."],
      ["Material adjunto", s.material],
    ], [3100, 7006]),
  ];
}

const platformSheets = [
  {
    code: "P1", name: "Diseño inverso de LDT y lentes", title: "Método de diseño inverso de una óptica para alumbrado vial",
    description: "Plataforma prevista para partir de la geometría y los requisitos funcionales de una calle o vía y proponer la geometría de lente y la distribución fotométrica LDT que mejor responde a esos requisitos. La oportunidad está en cerrar el ciclo entre la necesidad de la vía, la óptica realizable, la luminaria y la verificación fotométrica, evitando un proceso manual de iteración de ensayo y error.",
    protection: "Prioridad muy alta para análisis de patente. Debe evaluarse también diseño industrial de las geometrías visibles que no estén exclusivamente impuestas por su función, y secreto empresarial para datasets, modelos de optimización y reglas de fabricación.",
    evidence: "Que la solución produce una distribución objetivo o una mejora medible —cumplimiento, potencia, uniformidad, deslumbramiento, material, número de iteraciones— y que la lente puede fabricarse dentro de las restricciones definidas.",
    problem: "Obtener una óptica viable que cumpla simultáneamente el objetivo luminotécnico de una vía y las restricciones físicas y productivas del producto.",
    solution: "Generar y seleccionar una geometría de lente y un LDT mediante un flujo inverso que usa la geometría de vía, los objetivos fotométricos y los límites de fabricación/luminaria.",
    effect: "Distribución luminosa verificable, menor iteración de diseño y solución físicamente fabricable; comparar contra el flujo manual o una óptica de referencia.",
    variants: "Diferentes tipologías de vía, LEDs, matrices, materiales, restricciones térmicas, criterios de fabricación y objetivos de optimización.",
    material: "Requisitos de vía, CAD de lentes, LDT de salida, simulaciones, iteraciones, restricciones de fabricación y resultados comparativos."
  },
  {
    code: "P2", name: "Motor paramétrico de luminaria", title: "Configuración fotométrica y térmica paramétrica de luminarias",
    description: "Motor que desacopla la distribución espacial contenida en el LDT de la condición operativa real de la luminaria. Calcula flujo útil, potencia y eficacia a partir de LED, corriente, tensión, pérdidas ópticas/eléctricas y límites térmicos, incluido el límite de la lente. Permite que una misma familia óptica se evalúe con configuraciones de producto reales y seguras.",
    protection: "Analizar patente de método/sistema si la combinación de modelado, límites físicos y selección produce un efecto técnico nuevo. Mantener como secreto curvas, coeficientes, datos de componentes y reglas de configuración.",
    evidence: "Que la separación LDT-flujo operativo evita configuraciones no seguras, predice mejor el desempeño o permite seleccionar una alternativa técnicamente superior con métricas térmicas y fotométricas reproducibles.",
    problem: "Configurar una luminaria sin confundir la fotometría espacial con el flujo, potencia y temperatura reales de cada configuración de producto.",
    solution: "Normalizar la fotometría y recomponer el punto operativo desde parámetros LED, eléctricos, térmicos y ópticos, aplicando restricciones físicas del conjunto.",
    effect: "Configuración segura, flujo útil y eficacia coherentes con el producto físico; validar frente a ensayos, simulación térmica o datos de laboratorio.",
    variants: "Familias de LED, CRI/CCT, drivers, ópticas, cuerpos, límites de temperatura, pérdidas y criterios de selección.",
    material: "Esquemas del motor, tablas o curvas LED, modelos térmicos, LDT normalizados, ensayos y trazas de selección."
  },
  {
    code: "P3", name: "SALVI Tunnel Engine", title: "Optimización técnico-fotométrica y control de iluminación de túneles",
    description: "Plataforma de cálculo de túneles conforme a CIE 88 y CIE 140, con perfiles longitudinales, diseño de luminarias por zonas, tratamiento bidireccional asimétrico de portales, verificación con LDT y radiosidad, y plan de control DALI/Smartec. El valor diferencial potencial no está en aplicar la norma, sino en las combinaciones técnicas que traducen requisitos asimétricos en una instalación físicamente realizable y eficiente.",
    protection: "Proteger principalmente como secreto empresarial y software. Evaluar patente CII solo para una combinación nueva de perfil, validación, optimización de capas físicas/refuerzo y control que tenga una ventaja técnica demostrable frente al estado de la técnica.",
    evidence: "Mejora de energía, continuidad del perfil, cumplimiento por zona, uniformidad/deslumbramiento y ausencia de soluciones físicamente inviables; comparar con una estrategia de diseño/control convencional.",
    problem: "Diseñar y controlar un túnel con exigencias de entrada distintas en ambos portales sin sobredimensionar ni introducir discontinuidades o incumplimientos.",
    solution: "Generar perfiles y zonas asimétricas, seleccionar luminarias y capas de refuerzo, verificar CIE 140 y convertir el resultado en escenas DALI/Smartec controlables.",
    effect: "Cumplimiento luminotécnico y reducción de energía en una instalación real; ensayos o simulaciones multi-escenario con trazabilidad de control.",
    variants: "Uno o dos tubos, sentidos de tráfico, reflectancias, ópticas, radiosidad, velocidades, escenarios de luz exterior y estrategias de control.",
    material: "Arquitectura del motor, casos de cálculo, LDT, perfiles, resultados CIE, pruebas, curvas de control y exportación Smartec."
  },
  {
    code: "P4", name: "Salvi GIS y cálculo solar-fotométrico", title: "Diseño georreferenciado de alumbrado con evaluación solar y fotométrica",
    description: "Plataforma de apoyo a la proyección macro y de detalle que trabaja sobre el mapa, calcula calles tipo y vías reales, y conecta la geometría georreferenciada con el cálculo solar y fotométrico. Su función es llevar las condiciones reales de orientación, sombras, implantación y desempeño lumínico a una decisión técnica de diseño, no limitarse a pintar resultados sobre un mapa.",
    protection: "El GIS, interfaces y datos deben protegerse por copyright, secreto, base de datos y contratos. Evaluar patente CII si el método de uso de datos geográficos y solares produce una selección/control técnico nuevo y cuantificable sobre un sistema de alumbrado.",
    evidence: "Reducción de error, sobredimensionamiento, energía o incumplimiento respecto a un diseño no georreferenciado; validar el beneficio con casos reales y comparativas reproducibles.",
    problem: "Transformar condiciones geográficas y solares específicas de una vía en requisitos fiables de diseño y operación de alumbrado.",
    solution: "Integrar la geometría de la instalación, el contexto solar y las reglas fotométricas para calcular y seleccionar soluciones a escala de calle tipo o de mapa real.",
    effect: "Diseño más ajustado a la ubicación, con reducción medible de desviación energética o luminotécnica; documentar escenarios y resultados.",
    variants: "Fuentes geográficas, modelos solares, mallas urbanas, clases de vía, sensores, escenarios horarios, ópticas y objetivos de diseño.",
    material: "Casos GIS, modelos de entrada, mapas/sombras, resultados solares y fotométricos, comparación con metodología de referencia."
  },
  {
    code: "P5", name: "Cálculo y diseño de columnas", title: "Columna de alumbrado y método constructivo de alto desempeño",
    description: "Aplicación para calcular y diseñar columnas de acero, aluminio y hormigón pretensado. Debe identificar si, además del cálculo, existen soluciones nuevas de sección, unión, anclaje, armado, pretensado, montaje, durabilidad o fabricación que resuelvan un problema físico concreto. Es la línea con mayor posibilidad de obtener derechos sobre un producto tangible y observable.",
    protection: "Prioridad muy alta para patente o modelo de utilidad cuando exista una ventaja técnica de producto. Complementar con diseño industrial para la apariencia no exclusivamente funcional y secreto para reglas de cálculo, utillajes o procesos.",
    evidence: "Resultados estructurales, de durabilidad, fabricación, peso, coste o montaje frente a soluciones conocidas; deben referirse a una configuración concreta y no solo a un dimensionado numérico.",
    problem: "Mejorar la resistencia, durabilidad, instalación, fabricación o coste de una columna de alumbrado manteniendo las exigencias de servicio.",
    solution: "Nueva configuración estructural, material, unión, anclaje, armado o proceso de fabricación aplicable a columnas de acero, aluminio o hormigón pretensado.",
    effect: "Ventaja técnica apreciable y verificable en uso o fabricación; aportar cálculo, ensayo, prototipo o comparación.",
    variants: "Materiales, secciones, alturas, uniones, cimentaciones, recubrimientos, pretensado, procesos y accesorios.",
    material: "Planos CAD, memorias de cálculo, FEA/ensayos, prototipos, proceso de fabricación, fotos y resultados comparativos."
  },
  {
    code: "P6", name: "Configurador de producto e integración industrial", title: "Configuración trazable de luminarias y columnas desde ingeniería a producción",
    description: "Configurador que crea luminarias y columnas con su BOM y fases de producción, conectado a las aplicaciones de ingeniería y al ERP. Su valor es mantener una única configuración técnica desde el cálculo y selección del producto hasta la lista de materiales, compra, fabricación, calidad, venta, entrega y activo instalado. La parte general de flujo empresarial no es una patente fuerte, pero el acoplamiento técnico puede contener activos diferenciadores.",
    protection: "Copyright y secreto empresarial como capa principal. Evaluar patente solo si el modelo de datos y las validaciones producen una configuración, fabricación o control técnico de equipos físicos que no se obtenga con un ERP/configurador convencional.",
    evidence: "Menos errores de configuración, incompatibilidades o retrabajos, y trazabilidad exacta entre parámetros de cálculo, BOM, ruta, control y activo instalado; documentar reglas técnicas automáticas.",
    problem: "Evitar que la configuración de ingeniería se pierda o se modifique manualmente al pasar a producto, BOM, producción y operación.",
    solution: "Modelo versionado que vincula los parámetros técnicos de luminaria/columna con componentes, operaciones de fabricación, calidad, pedido y activo georreferenciado.",
    effect: "Configuración fabricable y verificable sin pérdida de integridad; demostrar reducción de errores y control técnico de compatibilidades.",
    variants: "Familias de producto, reglas de compatibilidad, BOM alternativas, rutas, controles de calidad, conectores ERP/Smartec/GIS y formatos de datos.",
    material: "Modelo de datos, reglas de validación, ejemplos de configuraciones, BOM, rutas, trazas de versión y casos de extremo a extremo."
  },
  {
    code: "P7", name: "Auditoría móvil en lazo cerrado", title: "Medición móvil georreferenciada y ajuste automático de alumbrado",
    description: "Proyecto previsto para medir luminancia e iluminancia de forma continua desde un vehículo mediante luminancímetro/luxómetro, asociar los datos al tramo y activo correspondiente y compararlos con el diseño original. Con esa discrepancia, Smartec podrá proponer o ejecutar ajustes de nivel para recuperar cumplimiento y reducir consumo. Cierra el ciclo entre diseño, instalación, medida real y operación.",
    protection: "Oportunidad relevante de patente de sistema o método CII si se concreta una adquisición móvil validada, corrección de condiciones de medida, correlación con el modelo de diseño y lógica de control con efecto técnico. Proteger modelos de corrección, datos y umbrales como secreto.",
    evidence: "Repetibilidad y precisión de las medidas en movimiento; garantía de que representan la condición luminotécnica relevante; reducción demostrable de incumplimiento y energía tras el ajuste automático.",
    problem: "Auditar extensas redes de alumbrado y corregir desviaciones respecto al diseño sin campañas manuales lentas ni ajustes basados en datos no equivalentes.",
    solution: "Vehículo instrumentado que adquiere una señal continua, la sincroniza con ubicación/contexto y diseño, identifica desviaciones y transmite una orden o consigna verificable a Smartec.",
    effect: "Ajuste en lazo cerrado que mantiene los niveles de servicio con menor consumo; validar con campañas repetidas, antes/después y trazas de control.",
    variants: "Luminancia o iluminancia, sensores y calibración, posicionamiento, normalización geométrica, velocidad, clima, tráfico, tipo de vía, control manual/asistido/automático.",
    material: "Arquitectura de vehículo e instrumentos, protocolo de calibración, modelo de correlación, telemetría, casos reales, informes antes/después y comandos Smartec."
  },
].flatMap(platformSheet);

const intro = [
  p("INFORME DE IDENTIFICACIÓN Y ESTRATEGIA DE PROPIEDAD INTELECTUAL", { bold: true, color: BLUE, size: 34, after: 150, line: 360 }),
  p("Ecosistema digital end-to-end de alumbrado exterior y túneles", { color: BLUE2, size: 25, after: 600 }),
  p("Documento de trabajo para la reunión con el agente de propiedad industrial e intelectual", { italics: true, color: GRAY, size: 20, after: 1200 }),
  p("SALVI · Julio de 2026", { bold: true, color: BLUE, size: 19, after: 220 }),
  p("Finalidad: identificar activos, priorizar oportunidades de protección y preparar las decisiones que requieren una búsqueda profesional de anterioridades y una estrategia de registro.", { color: GRAY, size: 18, after: 800 }),
  p("Advertencia", { bold: true, color: "FFFFFF", size: 18, shading: undefined, after: 0 }),
  new Table({ rows: [new TableRow({ children: [cell("Este informe es una base estratégica y técnica, no un dictamen jurídico ni un análisis de libertad de operación (FTO). La patentabilidad, titularidad y alcance de cada derecho deben confirmarse por el agente tras revisar la documentación, las fechas de divulgación y las anterioridades.", 10106, { shading: AMBER, size: 18 })] })], width: { size: 10106, type: WidthType.DXA }, columnWidths: [10106] })
];

const content = [
  ...intro,
  heading("1. Resumen ejecutivo", 1, { pageBreakBefore: true }),
  p("SALVI está construyendo una plataforma industrial integrada que sustituye el intercambio manual de documentos entre las fases del alumbrado por una continuidad digital de datos, decisiones y evidencias. La propuesta de valor no es una colección de aplicaciones: es un sistema conectado desde la conversación y la necesidad de una administración hasta el proyecto, la fabricación, la implantación, la monitorización, el mantenimiento y la auditoría energética."),
  p("La protección debe ser acumulativa. No conviene intentar patentar el conjunto como «software de gestión de alumbrado», porque gran parte de esa formulación sería una automatización o una regla de negocio. Sí existen líneas con potencial de patente o modelo de utilidad cuando se expresan como soluciones técnicas concretas: diseño inverso de ópticas y LDT, algoritmos que producen un efecto técnico verificable sobre una instalación física, estructuras de columnas y sus uniones, y métodos de control/optimización ligados a luminarias, sensores, geometría o restricciones térmicas y energéticas."),
  p("La recomendación inmediata es abrir cuatro expedientes de alta prioridad: (i) ópticas/LDT y motor paramétrico de luminaria; (ii) columnas y elementos constructivos; (iii) métodos técnico-fotométricos de túneles, solar y optimización; y (iv) auditoría móvil en lazo cerrado. En paralelo, debe formalizarse un programa de secreto empresarial para datos, reglas de optimización, modelos paramétricos, configuradores y know-how de fabricación."),
  heading("2. Alcance y base de este informe", 1),
  p("El análisis se basa en la explicación recibida y en el conocimiento técnico disponible del proyecto de cálculo de túneles desarrollado conjuntamente. No presupone que todos los módulos estén ya publicados o comercializados; esa información es decisiva y debe completarse con el agente."),
  table(["Fuente", "Contenido utilizado"], [
    ["Información de SALVI", "Smartec; GIS; cálculo solar georreferenciado; cálculo fotométrico de vías y mapa; túneles; diseño de LDT y lentes; cálculo/diseño de columnas; configurador de producto; ERP, operaciones y futura auditoría móvil."],
    ["Proyecto Tunnel Engine", "Motor CIE 88:2004 y CIE 140:2019; diseño por zonas; túneles bidireccionales asimétricos; LDT; radiosidad; optimización; motor LED paramétrico; control DALI y exportación a Smartec; informes y Excel."],
    ["Marco de protección", "España y Unión Europea. Se recomienda validar el alcance territorial real de negocio antes de presentar solicitudes."],
  ], [2200, 7906]),
  heading("3. El activo estratégico: el hilo digital de SALVI", 1),
  p("El núcleo diferenciador es la continuidad de un modelo de datos técnico, georreferenciado y comercial. Los documentos son resultados generados desde ese modelo —no la interfaz manual entre departamentos— y las decisiones tomadas en una fase llegan estructuradas a la siguiente."),
  table(["Fase", "Sistema / capacidad", "Dato o evidencia que debe mantenerse trazable"], [
    ["Necesidad y planificación", "Cartera de clientes, oportunidades y Salvi GIS", "Necesidad, municipio, alcance, hipótesis, ubicación y alternativas."],
    ["Proyecto", "Cálculo solar y fotométrico en calle tipo y mapa; túneles", "Geometría, clases de vía, resultados, restricciones normativas, energía y selección técnica."],
    ["Diseño de producto", "LDT/ópticas, luminarias y columnas", "Requisitos de vía, diseño óptico, comportamiento térmico, mecánico y especificaciones de fabricación."],
    ["Industrialización", "Configurador de luminarias/columnas, BOM y fases", "Configuración aprobada, versiones, componentes, rutas, calidad y coste."],
    ["Operación", "ERP, Smartec, GIS y futura auditoría móvil", "Pedido, fabricación, activo instalado, ubicación, mantenimiento, telemetría, medida real de luz, energía y auditoría."],
  ], [1800, 3300, 5006]),
  p("La estructura de datos, las reglas de transformación entre fases y el vínculo bidireccional entre diseño y desempeño real deben tratarse como activos de alto valor. Puede haber base para reivindicaciones técnicas solo si ese modelo provoca o permite un efecto técnico específico —por ejemplo, configuración/control fiable de activos físicos—; en el resto de casos será principalmente secreto empresarial, derecho de autor, base de datos y contrato."),
  heading("4. Inventario de activos y modalidades de protección", 1),
  table(["Activo", "Contenido identificable", "Protección principal", "Prioridad"], [
    ["Smartec + GIS", "Inventario georreferenciado, operación, mantenimiento, monitorización y flujo de decisiones.", "Copyright, secreto empresarial, base de datos, marca, contratos; patente solo para efecto técnico concreto.", "Alta"],
    ["Motor de cálculo vial y solar", "Cálculo y optimización de calles tipo y sobre mapa; resultado georreferenciado y selección de soluciones.", "Secreto/copyright; patente si el método técnico es nuevo y medible.", "Alta"],
    ["Tunnel Engine", "CIE 88/CIE 140; L20-Lseq-Lth; zonas asimétricas; verificación; radiosidad; DALI/Smartec; optimización.", "Secreto/copyright; posible patente CII para combinaciones técnicas no normativas.", "Alta"],
    ["Diseño de LDT y lentes", "Síntesis desde geometría y requisitos de vía; generación/validación de distribución óptica.", "Patente y/o secreto; diseño industrial para geometrías no exclusivamente funcionales.", "Muy alta"],
    ["Columnas", "Diseño/cálculo de columnas de acero, aluminio y hormigón pretensado.", "Patente/modelo de utilidad para solución constructiva; diseño industrial; secreto de cálculo/fabricación.", "Muy alta"],
    ["Configurador y BOM", "Configuración de luminarias/columnas, lista de materiales, rutas y producción.", "Secreto/copyright; patente solo si resuelve un problema técnico de configuración/fabricación.", "Alta"],
    ["Auditoría móvil en lazo cerrado", "Medición continua de luminancia/iluminancia desde vehículo; comparación georreferenciada con diseño; ajuste automático por Smartec.", "Patente CII/sistema técnico si la captura, normalización, comparación y control son nuevos; secreto de modelos y datos.", "Muy alta"],
    ["ERP integrado", "CRM, ventas, compras, inventario, producción, calidad, contabilidad y tesorería.", "Copyright, secreto empresarial, contratos, marca; generalmente no patente por sí solo.", "Media"],
  ], [1750, 3100, 3500, 1756]),
  heading("5. Oportunidades de patente o modelo de utilidad", 1),
  p("Las opciones siguientes no son conclusiones de patentabilidad. Son hipótesis de invención que merecen una ficha técnica confidencial y una búsqueda de anterioridades. La clave será describir el problema técnico, los rasgos nuevos, el efecto técnico verificable y las variantes, no la interfaz ni el objetivo comercial."),
  table(["Código", "Hipótesis de invención", "Valor técnico que debe demostrarse", "Vía sugerida"], [
    ["P1", "Diseño inverso de ópticas/lentes y generación de LDT a partir de geometría de vía, requisitos luminotécnicos, restricciones de fabricación y comportamiento de luminaria.", "Menor número de iteraciones; distribución fotométrica objetivo; cumplimiento y reducción cuantificable de potencia/material; geometría de lente realizable.", "Patente nacional/EPO; preservar como secreto los modelos, datasets y heurísticas."],
    ["P2", "Motor paramétrico de luminaria que separa la distribución espacial del LDT de flujo/potencia operativa y calcula rendimiento desde LED, corriente, tensión, pérdidas y límite térmico de lentes.", "Configuración segura y reproducible; límite térmico; flujo útil/eficacia y selección de potencia coherente con el producto físico.", "Patente CII y/o procedimiento técnico; secreto en datos de producto y curvas."],
    ["P3", "Optimización de túneles que combina portales con exigencias asimétricas, perfil continuo, comprobaciones fotométricas, capas físicas de refuerzo y control DALI.", "Mejor cumplimiento y menor energía sin discontinuidades de luminancia ni configuraciones físicamente inviables. Los elementos exigidos por CIE, aislados, no serán novedosos.", "Patente CII solo si la combinación/algoritmo y efecto técnico superan anterioridades; secreto como alternativa."],
    ["P4", "Cálculo solar georreferenciado vinculado a fotometría y elección de solución para una vía real, considerando sombras, orientación, geometría, energía y desempeño nocturno.", "Predicción o control técnico mejorado de un sistema físico; reducción demostrable de desviación energética, sobredimensionamiento o incumplimiento.", "Patente CII si hay solución técnica específica; secreto de modelos y fuentes de datos."],
    ["P5", "Columna de alumbrado, unión, anclaje, sección, proceso o armado que aporte resistencia, durabilidad, montaje, coste o comportamiento verificable en acero/aluminio/hormigón pretensado.", "Ventaja estructural o de fabricación concretamente medible, no solo una dimensión calculada.", "Patente o modelo de utilidad en España; diseño industrial en paralelo si hay apariencia distintiva."],
    ["P6", "Formato/estructura de datos que traslada configuración técnica de fotometría, óptica, BOM, control y activo instalado para configurar u operar equipos sin pérdida de integridad.", "El dato debe tener uso técnico y producir efecto en el sistema, no servir solo a gestión administrativa.", "Explorar con prudencia como patente CII; protección principal: secreto, copyright y contratos."],
    ["P7", "Auditoría móvil: vehículo con luminancímetro/luxómetro que adquiere medidas continuas, las vincula a posición, contexto y diseño, detecta desviaciones y ordena ajustes de control mediante Smartec.", "Medición fiable y repetible desde vehículo; corrección de la geometría y condiciones de adquisición; comparación con diseño y ajuste que reduzca incumplimiento/energía con garantías técnicas.", "Patente de sistema/método CII si existe solución concreta; proteger como secreto los modelos de corrección, umbrales y datos."],
  ], [800, 3650, 3500, 2156]),
  p("La línea P1 es la candidata más clara para una primera solicitud: combina una óptica física, un proceso de diseño y un resultado medible. P5 también merece una revisión temprana porque puede desembocar en reivindicaciones de producto, habitualmente más directas de defender frente a copias. P7 es una oportunidad muy relevante si se diseña desde el inicio como un sistema técnico de medida y control: el sensor por sí solo, o una comparación genérica con un proyecto, no bastarán. P2-P4 y P7 pueden ser protegibles como invenciones implementadas en ordenador cuando el expediente se centre en su contribución técnica, no en cálculo abstracto o gestión."),
  ...platformSheets,
  heading("6. Lectura jurídica práctica para el agente", 1, { pageBreakBefore: true }),
  p([run("Programas de ordenador. ", { bold: true, color: BLUE }), run("En España los programas originales, su documentación preparatoria y manuales tienen protección por derecho de autor; esta protege la expresión, no las ideas o principios. En el empleo, los derechos de explotación del software creado por un empleado en sus funciones corresponden, salvo pacto, al empresario. ")]),
  p([run("Patentes de software. ", { bold: true, color: BLUE }), run("En Europa no se protege un programa «como tal», pero sí puede haber una invención implementada en ordenador con carácter técnico y un efecto técnico adicional. Las reivindicaciones han de recoger los rasgos esenciales que producen ese efecto. Para SALVI, la redacción debe anclarse a la geometría, óptica, luminaria, columna, sensor, control, cálculo físico o proceso de fabricación, según el caso.")]),
  p([run("Secreto empresarial. ", { bold: true, color: BLUE }), run("Es especialmente útil para algoritmos, coeficientes, reglas de optimización, datos de producto, curvas térmicas, BOM, procesos, parámetros de fabricación y arquitectura de integración. Su condición legal exige que la información sea secreta, tenga valor empresarial y esté sujeta a medidas razonables de protección; no basta con llamarla confidencial.")]),
  p([run("Diseño, marca y modelo de utilidad. ", { bold: true, color: BLUE }), run("La apariencia externa de la luminaria, columna, interfaz o iconos puede protegerse como diseño si es nueva y tiene carácter singular; una solución constructiva de producto con ventaja técnica puede encajar en patente o modelo de utilidad. Las marcas protegen los signos que distinguen productos y servicios. Estas capas pueden coexistir.")]),
  heading("7. Lo que no debe presentarse como patente sin acotarlo", 1),
  bullet("El concepto genérico de «plataforma end-to-end para gestionar alumbrado» o un flujo comercial/ERP: valioso, pero normalmente de naturaleza organizativa o de negocio."),
  bullet("Un vehículo con un luxómetro/luminancímetro que simplemente registre valores y los muestre en un mapa: la opción técnica a proteger debe estar en la adquisición validada, normalización, correlación con el diseño y/o control automático con efecto demostrable."),
  bullet("La aplicación directa de normas CIE, DALI, LDT, GIS o ERP, por sí sola: puede ser necesaria, pero no prueba novedad ni actividad inventiva."),
  bullet("Un cálculo conocido ejecutado en un ordenador, sin efecto técnico adicional demostrable."),
  bullet("Funciones de interfaz, dashboards o generación de documentos, salvo que formen parte inseparable de una solución técnica concreta."),
  p("Esto no reduce su valor: dichas capas deben protegerse por derecho de autor, secreto empresarial, diseño, marca, contratos, control de acceso y velocidad de ejecución comercial."),
  heading("8. Programa de protección recomendado", 1),
  table(["Horizonte", "Acción", "Resultado"], [
    ["0–15 días", "Congelar divulgaciones públicas de P1–P7; identificar demos, ofertas, repositorios, ferias, publicaciones y accesos de terceros; firmar/actualizar NDA y cláusulas de titularidad.", "Mapa de riesgo de novedad y cadena de titularidad."],
    ["0–30 días", "Crear una ficha de invención por P1–P7 con problema técnico, solución, variantes, pruebas, autores, fechas y material gráfico. Solicitar búsqueda de anterioridades internacional priorizada.", "Decisión informada de presentación y borrador de reivindicaciones."],
    ["30–60 días", "Presentar primero las solicitudes seleccionadas antes de publicar o comercializar los rasgos nuevos. Definir países objetivo y estrategia de prioridad/PCT/EPO con el agente.", "Prioridad preservada para los desarrollos núcleo."],
    ["30–90 días", "Implementar programa de secretos: clasificación, mínimo privilegio, repositorios privados, registro de accesos, versionado, offboarding y formación. Revisar contratos de empleados, colaboradores y proveedores.", "Prueba de medidas razonables y menor fuga de know-how."],
    ["Continuo", "Vigilancia de patentes, diseños y marcas; revisión trimestral del embudo de I+D; marcar cada nueva invención antes de demo/venta.", "Cartera viva y decisiones tempranas."],
  ], [1450, 5600, 3056]),
  heading("9. Evidencias que debe reunir SALVI", 1),
  bullet("Cronología verificable: cuaderno de invención, tickets, actas, repositorios, versiones, prototipos, ensayos, facturas y entregas; indicar quién creó qué y cuándo."),
  bullet("Pruebas comparativas contra una solución conocida: energía, uniformidad, tiempo de cálculo, robustez, número de luminarias, temperatura, masa, coste o facilidad de fabricación."),
  bullet("Documentación técnica reproducible: esquemas de arquitectura, diagramas de flujo, ecuaciones, rango de parámetros, geometrías de lente/columna, BOM, capturas de resultados y variantes."),
  bullet("Para P7: arquitectura de adquisición móvil, calibración y trazabilidad de los instrumentos, posicionamiento/sincronización, criterio de correlación con el diseño y ensayos de la precisión del ajuste propuesto."),
  bullet("Titularidad: contratos laborales, encargos de desarrollo, cesiones de derechos, licencias de terceros, componentes open-source, LDTs y bases de datos. Confirmar que SALVI puede explotar y registrar lo que presenta."),
  bullet("Control de divulgación: acuerdos de confidencialidad, listas de acceso, presentaciones enviadas, pilotos, concursos públicos y publicaciones web. Cualquier divulgación previa debe declararse al agente."),
  heading("10. Preguntas para la reunión con el agente", 1),
  bullet("¿Qué módulos o características se han mostrado, ofertado, instalado o publicado, ante quién y en qué fecha?"),
  bullet("¿Qué problema técnico y qué métrica de mejora puede acreditarse para P1–P7?"),
  bullet("En la auditoría móvil, ¿cómo se garantiza que una medida tomada en movimiento representa la condición luminotécnica relevante y qué corrección/control aporta una mejora técnica nueva?"),
  bullet("¿Qué inventores participaron y existe cesión contractual expresa a la sociedad para empleados, consultores y proveedores?"),
  bullet("¿Qué mercados de fabricación y venta justifican una estrategia España, EPO y/o PCT?"),
  bullet("¿Qué familias de patentes de óptica, alumbrado adaptativo, GIS/solar, cálculo de túneles y columnas deben investigarse para patentabilidad y libertad de operación?"),
  bullet("¿Qué nombres, logotipos, interfaces, luminarias y columnas deben registrarse como marca o diseño, y en qué clases/territorios?"),
  heading("11. Conclusión", 1),
  p("SALVI dispone de una posición especialmente interesante porque conecta conocimiento de producto físico, ingeniería luminotécnica, fotometría, energía, geografía, fabricación y operación. Esa combinación permite que parte de la innovación trascienda el software administrativo y se formule como soluciones técnicas protegibles. La prioridad debe ser presentar y documentar primero aquello que puede copiarse observando el producto o su funcionamiento —ópticas, lentes, columnas y métodos técnicos desplegados— y preservar como secreto los modelos, parámetros, datos, procesos y reglas cuyo valor depende de no ser conocidos."),
  p("El resultado recomendado de la reunión es una cartera inicial priorizada de 3–5 expedientes, un plan de búsquedas y una lista de medidas internas de confidencialidad y titularidad. No conviene retrasar la evaluación de novedad: la comercialización o publicación anterior a una solicitud puede destruir la novedad."),
  heading("Anexo A. Referencias oficiales consultadas", 1),
  p([run("Estas referencias se incluyen como orientación para la conversación con el agente; no sustituyen su asesoramiento. ")], { after: 120 }),
  p([link("OEPM — Qué es la propiedad industrial y qué se puede proteger", "https://www.oepm.es/es/conoce-la-propiedad-industrial/informacion-general/que-es-la-PI-y-que-se-puede-proteger/")]),
  p([link("OEPM — Patentar software / invenciones implementadas en ordenador", "https://www.oepm.es/cs/OEPMSite/contenidos/Folletos/FOLLETO_3_PATENTAR_SOFTWARE/017-12_EPO_software_web.html")]),
  p([link("EPO Guidelines 2025 — Programas de ordenador y efecto técnico adicional", "https://www.epo.org/en/legal/guidelines-epc/2025/g_ii_3_6.html")]),
  p([link("EPO Guidelines 2025 — Reivindicaciones de invenciones implementadas en ordenador", "https://www.epo.org/en/legal/guidelines-epc/2025/f_iv_3_9.html")]),
  p([link("BOE — Ley de Propiedad Intelectual, Título VII: Programas de ordenador", "https://www.boe.es/eli/es/rdlg/1996/04/12/1/con/20200708")]),
  p([link("BOE — Ley 1/2019 de Secretos Empresariales", "https://boe.es/buscar/act.php?id=BOE-A-2019-2364&lang=es&p=20190221&tn=2")]),
  p([link("OEPM — Preguntas frecuentes: divulgación previa y novedad", "https://www.oepm.es/es/preguntas-frecuentes/index.html?modalidadFaq=modalidad.3&searchPage=19&temas=&tramitesFaq=")]),
  p([link("OEPM — Búsquedas retrospectivas e informes de antecedentes", "https://www.oepm.es/es/informacion-tecnologica/consultoria-a-medida/busquedas-retrospectiva/")]),
  p([link("OEPM — Diseño industrial", "https://www.oepm.es/cs/OEPMSite/contenidos/NORMATIVA/NormasSobreDisenio/NSDI_Nacionales/Ley_20_2003_7_julio_ProtecJuricaDisIndu.htm")]),
  p([link("EUIPO — Diseños de la Unión Europea", "https://www.euipo.europa.eu/en/designs")]),
];

const doc = new Document({
  creator: "SALVI",
  title: "Informe de Propiedad Intelectual y Patentes — Ecosistema Digital SALVI",
  description: "Documento de trabajo para agente de propiedad industrial e intelectual.",
  numbering: { config: [{ reference: "bullets", levels: [{ level: 0, format: "bullet", text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 480, hanging: 240 } } } }] }] },
  styles: { default: { document: { run: { font: "Aptos", size: 20, color: "222222" }, paragraph: { spacing: { after: 120, line: 276 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: "Aptos Display", size: 27, bold: true, color: BLUE }, paragraph: { spacing: { before: 340, after: 130 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: "Aptos Display", size: 22, bold: true, color: BLUE2 }, paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1 } },
    ] } },
  sections: [{ properties: { page: { margin: margins } }, headers: { default: new Header({ children: [p([run("SALVI · Informe de Propiedad Intelectual y Patentes", { color: GRAY, size: 16 })], { alignment: AlignmentType.LEFT, after: 0 })] }) }, footers: { default: new Footer({ children: [p([run("Confidencial · Documento de trabajo", { color: GRAY, size: 16 }), run("                         Página ", { color: GRAY, size: 16 }), new TextRun({ children: [PageNumber.CURRENT], font: "Aptos", size: 16, color: GRAY })], { alignment: AlignmentType.RIGHT, after: 0 })] }) }, children: content }]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync(out, buffer);
  console.log(out);
});
