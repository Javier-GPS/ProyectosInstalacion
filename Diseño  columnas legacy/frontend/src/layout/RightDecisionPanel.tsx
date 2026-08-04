import { useDecisionPanelContext, type ComplianceState } from "./DecisionPanelContext";
import { COMPLIANCE_ICON, COMPLIANCE_LABEL } from "../design-system/compliance";
import { KPICard } from "../design-system/KPICard";
import "./RightDecisionPanel.css";

function ComplianceIcon({ state }: { state: ComplianceState }) {
  return (
    <span className={`decision-compliance-icon decision-compliance-icon--${state}`}>
      {COMPLIANCE_ICON[state]}
    </span>
  );
}

export function RightDecisionPanel({
  collapsed,
  onToggle,
}: {
  collapsed: boolean;
  onToggle: () => void;
}) {
  const { data } = useDecisionPanelContext();

  return (
    <aside className={`decision-panel ${collapsed ? "decision-panel--collapsed" : ""}`}>
      <button className="decision-panel-toggle" onClick={onToggle}>
        {collapsed ? "«" : "Decisión »"}
      </button>

      {!collapsed && (
        <div className="decision-panel-body">
          {!data && (
            <div className="decision-panel-empty">
              Esta pantalla todavía no aporta datos de decisión. El estado, la norma aplicada, los
              indicadores clave y las acciones recomendadas aparecerán aquí cuando estén
              disponibles.
            </div>
          )}

          {data && (
            <>
              <div className="decision-panel-section-title">Estado general</div>
              <div className={`decision-compliance decision-compliance--${data.complianceState}`}>
                <ComplianceIcon state={data.complianceState} />
                <div>
                  <div className="decision-compliance-label">
                    {COMPLIANCE_LABEL[data.complianceState]}
                  </div>
                  <div className="decision-compliance-title">{data.title}</div>
                </div>
              </div>

              {data.standard && (
                <div className="decision-standard">
                  <span className="decision-standard-label">Norma aplicada</span>
                  <span>{data.standard}</span>
                </div>
              )}

              {data.kpis && data.kpis.length > 0 && (
                <>
                  <div className="decision-panel-section-title">Indicadores</div>
                  <div className="decision-kpi-stack">
                    {data.kpis.map((kpi) => (
                      <KPICard key={kpi.label} label={kpi.label} value={kpi.value} />
                    ))}
                  </div>
                </>
              )}

              {data.actions && data.actions.length > 0 && (
                <>
                  <div className="decision-panel-section-title">Motivo y acción recomendada</div>
                  <div className="decision-actions">
                    {data.actions.map((a, i) => (
                      <div className="decision-action" key={i}>
                        <div className="decision-action-message">{a.message}</div>
                        {a.recommendation && (
                          <div className="decision-action-recommendation">
                            → {a.recommendation}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </>
              )}
            </>
          )}
        </div>
      )}
    </aside>
  );
}
