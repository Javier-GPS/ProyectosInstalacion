import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type ComplianceState = "ok" | "warning" | "danger" | "pending";

export interface DecisionKPI {
  label: string;
  value: string;
}

export interface DecisionAction {
  message: string;
  recommendation?: string;
}

export interface DecisionPanelData {
  title: string;
  complianceState: ComplianceState;
  complianceLabel: string;
  standard?: string;
  kpis?: DecisionKPI[];
  actions?: DecisionAction[];
}

interface DecisionPanelContextValue {
  data: DecisionPanelData | null;
  setPanel: (data: DecisionPanelData | null) => void;
}

const DecisionPanelContext = createContext<DecisionPanelContextValue | undefined>(undefined);

export function DecisionPanelProvider({ children }: { children: ReactNode }) {
  const [data, setPanel] = useState<DecisionPanelData | null>(null);
  return (
    <DecisionPanelContext.Provider value={{ data, setPanel }}>
      {children}
    </DecisionPanelContext.Provider>
  );
}

export function useDecisionPanelContext(): DecisionPanelContextValue {
  const ctx = useContext(DecisionPanelContext);
  if (!ctx) {
    throw new Error("useDecisionPanelContext debe usarse dentro de DecisionPanelProvider");
  }
  return ctx;
}

/**
 * Hook para que una pantalla alimente el panel de decisión mientras está
 * montada. Se limpia automáticamente al desmontar (navegar a otra pantalla).
 */
export function useDecisionPanel(data: DecisionPanelData | null) {
  const { setPanel } = useDecisionPanelContext();

  useEffect(() => {
    setPanel(data);
    return () => setPanel(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(data)]);
}
