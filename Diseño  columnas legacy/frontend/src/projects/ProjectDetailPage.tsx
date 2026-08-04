import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createRevision,
  getProject,
  listRevisions,
  transitionProjectStatus,
  type ProjectStatus,
} from "../api/projects";
import { useActiveProject } from "./ActiveProjectContext";
import { useDecisionPanel } from "../layout/DecisionPanelContext";
import { ComplianceBadge } from "../design-system/ComplianceBadge";
import { complianceForProjectStatus } from "../design-system/compliance";
import "./shared.css";

const STATUS_OPTIONS: ProjectStatus[] = [
  "draft",
  "in_preparation",
  "in_review",
  "observed",
  "validated",
  "released",
  "archived",
  "cancelled",
  "blocked",
];

export function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { setActiveProject } = useActiveProject();

  const projectQuery = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId!),
    enabled: Boolean(projectId),
  });

  const revisionsQuery = useQuery({
    queryKey: ["revisions", projectId],
    queryFn: () => listRevisions(projectId!),
    enabled: Boolean(projectId),
  });

  useEffect(() => {
    if (projectQuery.data) {
      setActiveProject(projectQuery.data);
    }
  }, [projectQuery.data, setActiveProject]);

  const project = projectQuery.data;
  const revisionCount = revisionsQuery.data?.items.length ?? 0;

  useDecisionPanel(
    project
      ? {
          title: `${project.name} · ${project.project_code}`,
          complianceState: complianceForProjectStatus(project.status),
          complianceLabel: project.status,
          standard: "EN 40 (edición congelada en revisión)",
          kpis: [
            { label: "Madurez", value: project.maturity },
            { label: "Revisiones", value: String(revisionCount) },
            { label: "País", value: project.country },
            { label: "Moneda", value: project.currency },
          ],
          actions:
            project.maturity === "M0" || project.maturity === "M1"
              ? [
                  {
                    message: "El proyecto está en fase preliminar (borrador/predimensionamiento).",
                    recommendation:
                      "Crea una revisión y define la geometría para avanzar hacia el cálculo interno (M2).",
                  },
                ]
              : [],
        }
      : null,
  );

  const [newRevisionCode, setNewRevisionCode] = useState("");
  const [statusReason, setStatusReason] = useState("");
  const [targetStatus, setTargetStatus] = useState<ProjectStatus>("in_preparation");

  const createRevisionMutation = useMutation({
    mutationFn: () => createRevision(projectId!, { revision_code: newRevisionCode }),
    onSuccess: () => {
      setNewRevisionCode("");
      queryClient.invalidateQueries({ queryKey: ["revisions", projectId] });
    },
  });

  const statusMutation = useMutation({
    mutationFn: () => transitionProjectStatus(projectId!, targetStatus, statusReason),
    onSuccess: () => {
      setStatusReason("");
      queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    },
  });

  function handleCreateRevision(e: FormEvent) {
    e.preventDefault();
    if (newRevisionCode.trim()) createRevisionMutation.mutate();
  }

  function handleStatusChange(e: FormEvent) {
    e.preventDefault();
    if (statusReason.trim()) statusMutation.mutate();
  }

  if (projectQuery.isLoading) return <div className="card">Cargando proyecto…</div>;
  if (projectQuery.isError || !project) {
    return <div className="inline-error">No se pudo cargar el proyecto.</div>;
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>
            {project.name} <span style={{ color: "var(--salvi-grey)" }}>· {project.project_code}</span>
          </h1>
          <p>
            {project.country} · {project.language.toUpperCase()} · {project.currency} ·{" "}
            <ComplianceBadge state={complianceForProjectStatus(project.status)} label={project.status} />{" "}
            <span className="maturity-badge">{project.maturity}</span>
          </p>
        </div>
        <button className="btn-secondary" onClick={() => navigate("/proyectos")}>
          ← Volver a proyectos
        </button>
      </div>

      <div className="section-title">Cambiar estado</div>
      <form className="card" onSubmit={handleStatusChange} style={{ maxWidth: 640 }}>
        <div className="form-grid">
          <label className="form-field">
            Nuevo estado
            <select
              value={targetStatus}
              onChange={(e) => setTargetStatus(e.target.value as ProjectStatus)}
            >
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label className="form-field">
            Motivo (obligatorio)
            <input value={statusReason} onChange={(e) => setStatusReason(e.target.value)} />
          </label>
        </div>
        <div className="form-actions">
          <button className="btn-primary" type="submit" disabled={statusMutation.isPending}>
            {statusMutation.isPending ? "Aplicando…" : "Aplicar cambio de estado"}
          </button>
        </div>
        {statusMutation.isError && (
          <div className="inline-error">No se pudo cambiar el estado.</div>
        )}
      </form>

      <div className="section-title">Revisiones</div>
      <form className="card" onSubmit={handleCreateRevision} style={{ maxWidth: 640, marginBottom: 16 }}>
        <div className="form-grid">
          <label className="form-field">
            Código de revisión (ej. R00)
            <input
              value={newRevisionCode}
              onChange={(e) => setNewRevisionCode(e.target.value)}
              maxLength={16}
              placeholder="R00"
            />
          </label>
        </div>
        <div className="form-actions">
          <button className="btn-primary" type="submit" disabled={createRevisionMutation.isPending}>
            {createRevisionMutation.isPending ? "Creando…" : "+ Nueva revisión"}
          </button>
        </div>
      </form>

      {revisionsQuery.data && revisionsQuery.data.items.length > 0 && (
        <div className="card" style={{ padding: 0 }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Código</th>
                <th>Tipo</th>
                <th>Madurez</th>
                <th>Congelada</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {revisionsQuery.data.items.map((rev) => (
                <tr key={rev.id}>
                  <td>{rev.revision_code}</td>
                  <td>{rev.revision_type}</td>
                  <td>
                    <span className="maturity-badge">{rev.maturity}</span>
                  </td>
                  <td>{rev.is_frozen ? "Sí" : "No"}</td>
                  <td>
                    <button
                      className="btn-secondary"
                      onClick={() => navigate(`/geometria?revisionId=${rev.id}`)}
                    >
                      Ir a geometría →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
