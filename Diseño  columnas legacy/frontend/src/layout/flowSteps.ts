export interface FlowStep {
  key: string;
  label: string;
  path: string;
  implemented: boolean;
}

// Flujo común de Salvi Studio (Design System v1.0, sección 6 "Navegación y flujos").
// Se omite el paso 8 "Operación" (Smartec/O&M): no forma parte del alcance de Columns,
// cuyo ciclo de vida termina en la liberación a fabricación (ver documento de contexto,
// sección 8, paso 12 "Congelar revisión").
export const FLOW_STEPS: FlowStep[] = [
  { key: "proyecto", label: "Proyecto", path: "/proyectos", implemented: true },
  { key: "geometria", label: "Geometría / Zona", path: "/geometria", implemented: true },
  { key: "datos", label: "Datos de entrada", path: "/cargas", implemented: false },
  { key: "calculo", label: "Cálculo / Simulación", path: "/calculo", implemented: false },
  { key: "optimizacion", label: "Optimización", path: "/optimizacion", implemented: false },
  { key: "resultados", label: "Resultados", path: "/acero", implemented: false },
  { key: "informe", label: "Informe", path: "/informes", implemented: false },
];
