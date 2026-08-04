import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import {
  addMast,
  createGeometryModel,
  validateGeometry,
  type GeometryModel,
  type Mast,
  type ValidationSummary,
} from "../api/geometry";
import { useDecisionPanel, type ComplianceState } from "../layout/DecisionPanelContext";
import "../projects/shared.css";

function complianceForValidation(validation: ValidationSummary): ComplianceState {
  if (validation.errors > 0 || validation.blocked > 0) return "danger";
  if (validation.warnings > 0) return "warning";
  return "ok";
}

export function GeometryPage() {
  const [searchParams] = useSearchParams();
  const revisionId = searchParams.get("revisionId");

  const [model, setModel] = useState<GeometryModel | null>(null);
  const [mast, setMast] = useState<Mast | null>(null);
  const [validation, setValidation] = useState<ValidationSummary | null>(null);

  const [height, setHeight] = useState(9);
  const [dBase, setDBase] = useState(159);
  const [dTop, setDTop] = useState(76);
  const [thickness, setThickness] = useState(4);

  const createModelMutation = useMutation({
    mutationFn: () => createGeometryModel({ project_revision_id: revisionId! }),
    onSuccess: (data) => setModel(data),
  });

  const addMastMutation = useMutation({
    mutationFn: () =>
      addMast(model!.id, {
        nominal_height_m: height,
        base_type: "plate",
        segments: [
          {
            segment_order: 1,
            piece_id: "T1",
            z_start_m: 0,
            z_end_m: height,
            physical_length_m: height,
            section_law: {
              law_type: "linear",
              parameter_json: {
                // El motor espera unidades SI (metros) — bottom_d_m/top_d_m/thickness_m.
                bottom_d_m: dBase / 1000,
                top_d_m: dTop / 1000,
                thickness_m: thickness / 1000,
              },
            },
          },
        ],
      }),
    onSuccess: (data) => setMast(data),
  });

  const validateMutation = useMutation({
    mutationFn: () => validateGeometry(model!.id),
    onSuccess: (data) => setValidation(data),
  });

  function handleCreateModel(e: FormEvent) {
    e.preventDefault();
    createModelMutation.mutate();
  }

  function handleAddMast(e: FormEvent) {
    e.preventDefault();
    addMastMutation.mutate();
  }

  useDecisionPanel(
    validation
      ? {
          title: `Modelo ${model?.id.slice(0, 8)} · fuste ${mast?.id.slice(0, 8)}`,
          complianceState: complianceForValidation(validation),
          complianceLabel: validation.quality_state,
          standard: "GEO-001..GEO-012 (Fase 2 · Geometría paramétrica)",
          kpis: [
            { label: "Comprobaciones", value: `${validation.passed}/${validation.total_checks}` },
            { label: "Errores", value: String(validation.errors) },
            { label: "Advertencias", value: String(validation.warnings) },
            { label: "Bloqueos", value: String(validation.blocked) },
          ],
          actions:
            validation.errors > 0 || validation.blocked > 0
              ? [
                  {
                    message: "El modelo geométrico no supera todas las reglas GEO.",
                    recommendation:
                      "Revisa diámetros, espesores y longitud de tramo; vuelve a validar tras corregir.",
                  },
                ]
              : validation.warnings > 0
                ? [
                    {
                      message: "Hay advertencias no bloqueantes en la geometría.",
                      recommendation: "Revísalas antes de avanzar a cálculo estructural.",
                    },
                  ]
                : [],
        }
      : model
        ? {
            title: `Modelo ${model.id.slice(0, 8)}`,
            complianceState: "pending",
            complianceLabel: "sin validar",
            standard: "GEO-001..GEO-012 (Fase 2 · Geometría paramétrica)",
            kpis: [{ label: "Nivel", value: model.lod }],
            actions: [
              {
                message: "El modelo geométrico todavía no se ha validado.",
                recommendation: "Añade el fuste y ejecuta las reglas GEO-001..012.",
              },
            ],
          }
        : null,
  );

  if (!revisionId) {
    return (
      <div>
        <div className="page-header">
          <div>
            <h1>Geometría</h1>
            <p>
              Fuste, tramos, secciones, conicidad y bases. El modelo geométrico se define sobre
              una revisión concreta de un proyecto.
            </p>
          </div>
        </div>
        <div className="card empty-state">
          Selecciona un proyecto y una revisión desde <strong>Proyectos</strong> — botón "Ir a
          geometría →" — para empezar a definir el fuste.
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Geometría</h1>
          <p>Revisión: {revisionId}</p>
        </div>
      </div>

      {!model && (
        <form className="card" onSubmit={handleCreateModel} style={{ maxWidth: 480 }}>
          <p style={{ marginTop: 0, fontSize: 13, color: "var(--salvi-grey)" }}>
            Crea el modelo geométrico paramétrico (nivel G1) para esta revisión.
          </p>
          <div className="form-actions" style={{ justifyContent: "flex-start" }}>
            <button className="btn-primary" type="submit" disabled={createModelMutation.isPending}>
              {createModelMutation.isPending ? "Creando…" : "Crear modelo geométrico"}
            </button>
          </div>
          {createModelMutation.isError && (
            <div className="inline-error">No se pudo crear el modelo geométrico.</div>
          )}
        </form>
      )}

      {model && (
        <>
          <div className="section-title">Modelo geométrico</div>
          <div className="card" style={{ marginBottom: 16 }}>
            <div>
              <strong>ID:</strong> {model.id}
            </div>
            <div>
              <strong>LOD:</strong> {model.lod} · <strong>Estado:</strong> {model.quality_state}
            </div>
          </div>

          <div className="section-title">Fuste (tramo único, sección circular)</div>
          <form className="card" onSubmit={handleAddMast} style={{ maxWidth: 640, marginBottom: 16 }}>
            <div className="form-grid">
              <label className="form-field">
                Altura sobre rasante (m)
                <input
                  type="number"
                  step="0.1"
                  value={height}
                  onChange={(e) => setHeight(Number(e.target.value))}
                />
              </label>
              <label className="form-field">
                Diámetro en base (mm)
                <input
                  type="number"
                  value={dBase}
                  onChange={(e) => setDBase(Number(e.target.value))}
                />
              </label>
              <label className="form-field">
                Diámetro en cabeza (mm)
                <input
                  type="number"
                  value={dTop}
                  onChange={(e) => setDTop(Number(e.target.value))}
                />
              </label>
              <label className="form-field">
                Espesor (mm)
                <input
                  type="number"
                  step="0.1"
                  value={thickness}
                  onChange={(e) => setThickness(Number(e.target.value))}
                />
              </label>
            </div>
            <div className="form-actions">
              <button className="btn-primary" type="submit" disabled={addMastMutation.isPending || Boolean(mast)}>
                {mast ? "Fuste creado" : addMastMutation.isPending ? "Guardando…" : "Añadir fuste"}
              </button>
            </div>
            {addMastMutation.isError && (
              <div className="inline-error">No se pudo crear el fuste. Revisa los valores.</div>
            )}
          </form>

          {mast && (
            <>
              <div className="section-title">Validación geométrica</div>
              <div className="card" style={{ maxWidth: 640 }}>
                <button className="btn-primary" onClick={() => validateMutation.mutate()} disabled={validateMutation.isPending}>
                  {validateMutation.isPending ? "Validando…" : "Ejecutar reglas GEO-001..GEO-012"}
                </button>

                {validation && (
                  <div style={{ marginTop: 14 }}>
                    <div>
                      <strong>Estado:</strong> {validation.quality_state} ·{" "}
                      <strong>Comprobaciones:</strong> {validation.passed}/{validation.total_checks}{" "}
                      superadas
                    </div>
                    {validation.errors > 0 && (
                      <div className="inline-error" style={{ marginTop: 8 }}>
                        {validation.errors} error(es).
                      </div>
                    )}
                    {validation.warnings > 0 && (
                      <div style={{ marginTop: 8, fontSize: 12.5, color: "var(--state-warning)" }}>
                        {validation.warnings} advertencia(s).
                      </div>
                    )}
                    {validation.blocked > 0 && (
                      <div className="inline-error" style={{ marginTop: 8 }}>
                        {validation.blocked} bloqueo(s) que requieren excepción.
                      </div>
                    )}
                  </div>
                )}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
