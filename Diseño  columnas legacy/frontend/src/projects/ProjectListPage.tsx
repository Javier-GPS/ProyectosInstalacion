import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { listProjects, type Project } from "../api/projects";
import { DataTable, type DataTableColumn } from "../design-system/DataTable";
import { ComplianceBadge } from "../design-system/ComplianceBadge";
import { complianceForProjectStatus } from "../design-system/compliance";
import "./shared.css";

export function ProjectListPage() {
  const navigate = useNavigate();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
  });

  const columns: DataTableColumn<Project>[] = [
    { key: "code", header: "Código", render: (p) => p.project_code },
    { key: "name", header: "Nombre", render: (p) => p.name },
    { key: "country", header: "País", render: (p) => p.country },
    {
      key: "status",
      header: "Estado",
      render: (p) => (
        <ComplianceBadge state={complianceForProjectStatus(p.status)} label={p.status} />
      ),
    },
    { key: "maturity", header: "Madurez", render: (p) => <span className="maturity-badge">{p.maturity}</span> },
  ];

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Proyectos</h1>
          <p>
            Cada proyecto fija cliente, país, ubicación, moneda, idioma y la norma activa.
            Todo trabajo de diseño ocurre dentro de un proyecto y su revisión.
          </p>
        </div>
        <button className="btn-primary" onClick={() => navigate("/proyectos/nuevo")}>
          + Nuevo proyecto
        </button>
      </div>

      {isLoading && <div className="card">Cargando proyectos…</div>}
      {isError && <div className="inline-error">No se pudo contactar con la API.</div>}

      {data && (
        <div className="card" style={{ padding: 0 }}>
          <DataTable
            columns={columns}
            rows={data.items}
            rowKey={(p) => p.id}
            onRowClick={(p) => navigate(`/proyectos/${p.id}`)}
            emptyMessage="Todavía no hay proyectos. Crea el primero para empezar el flujo de diseño."
          />
        </div>
      )}
    </div>
  );
}
