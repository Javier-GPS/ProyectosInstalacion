export interface NavItem {
  label: string;
  path: string;
  apiTag: string;
  description: string;
  implemented: boolean;
}

export interface NavGroup {
  title: string;
  items: NavItem[];
}

// Estructura de navegación siguiendo el flujo end-to-end (sección 8) y las vistas
// de sección 15 del documento de contexto general. `apiTag` referencia el tag
// real del OpenAPI del backend para esa sección.
export const NAV_GROUPS: NavGroup[] = [
  {
    title: "Proyecto",
    items: [
      {
        label: "Proyectos y revisiones",
        path: "/proyectos",
        apiTag: "projects",
        description:
          "Cliente, país, ubicación, oferta, revisión, estados y niveles de madurez M0-M4.",
        implemented: true,
      },
    ],
  },
  {
    title: "Entorno",
    items: [
      {
        label: "Ubicación y geodatos",
        path: "/entorno",
        apiTag: "actions",
        description:
          "Viento, nieve, sismo, altitud, corrosividad y parámetros nacionales propuestos por ubicación, confirmables por el usuario.",
        implemented: false,
      },
    ],
  },
  {
    title: "Geometría",
    items: [
      {
        label: "Fuste, tramos y secciones",
        path: "/geometria",
        apiTag: "geometry",
        description:
          "Modelo geométrico paramétrico: fuste, tramos, conicidad, brazos, puertas, cables y bases.",
        implemented: true,
      },
    ],
  },
  {
    title: "Cargas y cálculo",
    items: [
      {
        label: "Cargas y combinaciones",
        path: "/cargas",
        apiTag: "actions",
        description:
          "Casos de viento (barrido cada 30°), nieve, sismo, cables, montaje y combinaciones normativas.",
        implemented: false,
      },
      {
        label: "Cálculo estructural",
        path: "/calculo",
        apiTag: "structural",
        description:
          "Modelo de barras 3D, discretización, esfuerzos, deformaciones, estabilidad y fatiga.",
        implemented: false,
      },
    ],
  },
  {
    title: "Verificación por material",
    items: [
      {
        label: "Acero",
        path: "/acero",
        apiTag: "steel",
        description:
          "Materiales, secciones, soldadura, fatiga, galvanizado y fabricabilidad EN 40-5.",
        implemented: false,
      },
      {
        label: "Aluminio",
        path: "/aluminio",
        apiTag: "aluminium",
        description:
          "Extrusión, chapa 5083, plegado, HAZ, dirección de laminación y corrosión galvánica EN 40-6.",
        implemented: false,
      },
      {
        label: "Hormigón pretensado",
        path: "/hormigon",
        apiTag: "concrete",
        description:
          "Sección hueca centrifugada, pretensado, pérdidas, transporte y fabricación EN 40-4.",
        implemented: false,
      },
      {
        label: "Puertas y detalles locales",
        path: "/detalles",
        apiTag: "details",
        description: "Huecos, refuerzos, soporte interior y fijación de equipos.",
        implemented: false,
      },
    ],
  },
  {
    title: "Uniones y base",
    items: [
      {
        label: "Uniones y segmentación",
        path: "/uniones",
        apiTag: "joints",
        description:
          "Juntas telescópicas, bridas, soldaduras, logística de tramos >12 m y montaje.",
        implemented: false,
      },
      {
        label: "Placa base y anclajes",
        path: "/placa-base",
        apiTag: "baseplate",
        description: "Placas, cartelas, pernos L/J, familias 200/250/300 y anclajes.",
        implemented: false,
      },
      {
        label: "Cimentación",
        path: "/cimentacion",
        apiTag: "foundation",
        description: "Modos G1-G3, estabilidad geotécnica, geometría y coste.",
        implemented: false,
      },
    ],
  },
  {
    title: "Alternativas",
    items: [
      {
        label: "Catálogo y selección estándar",
        path: "/catalogo",
        apiTag: "catalog",
        description: "Filtrado, verificación, ranking y selección de referencia superior.",
        implemented: false,
      },
      {
        label: "Optimización",
        path: "/optimizacion",
        apiTag: "optimization",
        description: "Alternativas Pareto por coste, peso y CO2 con restricciones industriales.",
        implemented: false,
      },
    ],
  },
  {
    title: "Producción",
    items: [
      {
        label: "CAD y BOM",
        path: "/cad-bom",
        apiTag: "cad-bom",
        description: "STEP AP242, DXF, despiece, procesos, tolerancias e inspección.",
        implemented: false,
      },
      {
        label: "Catenarias",
        path: "/catenarias",
        apiTag: "catenary",
        description: "Hasta 6 cables de alumbrado suspendido: tensión, azimut e inclinación.",
        implemented: false,
      },
    ],
  },
  {
    title: "Documentación",
    items: [
      {
        label: "Informes",
        path: "/informes",
        apiTag: "reports",
        description: "Informe cliente, memoria extensa, informe de producción y liberación M0-M4.",
        implemented: false,
      },
      {
        label: "Validación y auditoría",
        path: "/validacion",
        apiTag: "validation",
        description: "Advertencias, excepciones, revisión de Oficina Técnica e historial.",
        implemented: false,
      },
    ],
  },
];

export const ALL_NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items);
