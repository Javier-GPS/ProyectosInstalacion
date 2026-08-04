import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useActiveProject } from "../projects/ActiveProjectContext";
import { NAV_GROUPS } from "./navigation";
import { RightDecisionPanel } from "./RightDecisionPanel";
import { Stepper } from "./Stepper";
import "./AppShell.css";

export function AppShell() {
  const { logout } = useAuth();
  const { activeProject } = useActiveProject();
  const [collapsed, setCollapsed] = useState(false);
  const [decisionCollapsed, setDecisionCollapsed] = useState(false);

  return (
    <div className="app-shell">
      <header className="app-topbar">
        <div className="app-topbar-brand">
          <span className="app-topbar-brand-mark">SALVI STUDIO</span>
          <span className="app-topbar-brand-app">Columns</span>
        </div>

        <div className="app-topbar-context">
          {activeProject ? (
            <>
              <span className="app-topbar-project">{activeProject.name}</span>
              <span className="app-topbar-sep">·</span>
              <span className="app-topbar-norm">EN 40 (edición congelada en revisión)</span>
            </>
          ) : (
            <span className="app-topbar-project app-topbar-project--empty">
              Ningún proyecto activo
            </span>
          )}
        </div>

        <button className="app-topbar-logout" onClick={logout}>
          Cerrar sesión
        </button>
      </header>

      <div className="app-body">
        <nav className={`app-sidenav ${collapsed ? "app-sidenav--collapsed" : ""}`}>
          <button className="app-sidenav-toggle" onClick={() => setCollapsed((c) => !c)}>
            {collapsed ? "»" : "« Contraer"}
          </button>

          {NAV_GROUPS.map((group) => (
            <div key={group.title} className="app-sidenav-group">
              {!collapsed && <div className="app-sidenav-group-title">{group.title}</div>}
              {group.items.map((item) => (
                <NavLink
                  key={item.path}
                  to={item.path}
                  className={({ isActive }) =>
                    `app-sidenav-item ${isActive ? "app-sidenav-item--active" : ""}`
                  }
                  title={item.label}
                >
                  {!collapsed ? item.label : item.label.slice(0, 2).toUpperCase()}
                  {!item.implemented && !collapsed && (
                    <span className="app-sidenav-badge">en construcción</span>
                  )}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <main className="app-main">
          <Stepper />
          <Outlet />
        </main>

        <RightDecisionPanel
          collapsed={decisionCollapsed}
          onToggle={() => setDecisionCollapsed((c) => !c)}
        />
      </div>
    </div>
  );
}
