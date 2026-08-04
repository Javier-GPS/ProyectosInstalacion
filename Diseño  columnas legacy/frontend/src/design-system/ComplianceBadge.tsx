import type { ComplianceState } from "../layout/DecisionPanelContext";
import { COMPLIANCE_ICON, COMPLIANCE_LABEL } from "./compliance";
import "./ComplianceBadge.css";

export function ComplianceBadge({
  state,
  label,
}: {
  state: ComplianceState;
  /** Texto a mostrar; por defecto la etiqueta funcional (Cumple/Revisar/...). */
  label?: string;
}) {
  return (
    <span className={`compliance-badge compliance-badge--${state}`}>
      <span className="compliance-badge-icon">{COMPLIANCE_ICON[state]}</span>
      {label ?? COMPLIANCE_LABEL[state]}
    </span>
  );
}
