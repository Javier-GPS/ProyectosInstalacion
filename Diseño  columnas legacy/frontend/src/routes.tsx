import { Navigate, Route, Routes } from "react-router-dom";
import { LoginPage } from "./auth/LoginPage";
import { RequireAuth } from "./auth/RequireAuth";
import { AppShell } from "./layout/AppShell";
import { ALL_NAV_ITEMS } from "./layout/navigation";
import { ProjectListPage } from "./projects/ProjectListPage";
import { ProjectCreatePage } from "./projects/ProjectCreatePage";
import { ProjectDetailPage } from "./projects/ProjectDetailPage";
import { GeometryPage } from "./geometry/GeometryPage";
import { PhasePlaceholder } from "./placeholder/PhasePlaceholder";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route
        path="/"
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/proyectos" replace />} />

        {/* Núcleo funcional */}
        <Route path="proyectos" element={<ProjectListPage />} />
        <Route path="proyectos/nuevo" element={<ProjectCreatePage />} />
        <Route path="proyectos/:projectId" element={<ProjectDetailPage />} />
        <Route path="geometria" element={<GeometryPage />} />

        {/* Resto de fases: placeholder navegable */}
        {ALL_NAV_ITEMS.filter((item) => !item.implemented).map((item) => (
          <Route key={item.path} path={item.path.slice(1)} element={<PhasePlaceholder item={item} />} />
        ))}

        <Route path="*" element={<Navigate to="/proyectos" replace />} />
      </Route>
    </Routes>
  );
}
