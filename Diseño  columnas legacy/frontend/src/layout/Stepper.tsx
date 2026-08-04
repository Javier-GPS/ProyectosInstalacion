import { useLocation, useNavigate } from "react-router-dom";
import { FLOW_STEPS } from "./flowSteps";
import "./Stepper.css";

function currentStepIndex(pathname: string): number {
  const idx = FLOW_STEPS.findIndex((s) => pathname === s.path || pathname.startsWith(s.path + "/"));
  return idx === -1 ? 0 : idx;
}

export function Stepper() {
  const location = useLocation();
  const navigate = useNavigate();
  const activeIndex = currentStepIndex(location.pathname);

  return (
    <nav className="stepper" aria-label="Flujo de diseño">
      {FLOW_STEPS.map((step, i) => {
        const isActive = i === activeIndex;
        const isPast = i < activeIndex;
        const isClickable = step.implemented;

        const stateClass = isActive
          ? "stepper-node--active"
          : isPast
            ? "stepper-node--done"
            : step.implemented
              ? "stepper-node--available"
              : "stepper-node--pending";

        return (
          <div className="stepper-step" key={step.key}>
            <button
              type="button"
              className={`stepper-node ${stateClass}`}
              disabled={!isClickable}
              onClick={() => isClickable && navigate(step.path)}
              title={step.implemented ? step.label : `${step.label} (en construcción)`}
            >
              {isPast ? "✓" : i + 1}
            </button>
            <span className={`stepper-label ${isActive ? "stepper-label--active" : ""}`}>
              {step.label}
            </span>
            {i < FLOW_STEPS.length - 1 && (
              <span className={`stepper-connector ${isPast ? "stepper-connector--done" : ""}`} />
            )}
          </div>
        );
      })}
    </nav>
  );
}
