import type { NavItem } from "../layout/navigation";
import "./PhasePlaceholder.css";

export function PhasePlaceholder({ item }: { item: NavItem }) {
  return (
    <div>
      <div className="page-header">
        <div>
          <h1>{item.label}</h1>
          <p>{item.description}</p>
        </div>
      </div>

      <div className="phase-placeholder-card">
        <div className="phase-placeholder-badge">En construcción</div>
        <p>
          Esta sección está reservada en la navegación y ya conectada conceptualmente con el
          backend (tag de API <code>{item.apiTag}</code>), pero su pantalla funcional todavía no
          se ha implementado en esta iteración.
        </p>
        <p>
          Se activará en una iteración siguiente reutilizando este mismo esqueleto de aplicación,
          siguiendo el plan de fases del documento de contexto general.
        </p>
      </div>
    </div>
  );
}
