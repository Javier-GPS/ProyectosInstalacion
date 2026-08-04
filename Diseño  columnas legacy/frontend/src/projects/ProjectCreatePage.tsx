import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { createProject, type ProjectCreateInput } from "../api/projects";
import "./shared.css";

const LANGUAGES = [
  { value: "es", label: "Español" },
  { value: "en", label: "English" },
  { value: "fr", label: "Français" },
  { value: "ca", label: "Català" },
  { value: "it", label: "Italiano" },
  { value: "pt", label: "Português" },
];

export function ProjectCreatePage() {
  const navigate = useNavigate();
  const [form, setForm] = useState<ProjectCreateInput>({
    name: "",
    country: "ES",
    language: "es",
    currency: "EUR",
    description: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function update<K extends keyof ProjectCreateInput>(key: K, value: ProjectCreateInput[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const project = await createProject({
        ...form,
        country: form.country.toUpperCase(),
      });
      navigate(`/proyectos/${project.id}`);
    } catch {
      setError("No se pudo crear el proyecto. Revisa los datos e inténtalo de nuevo.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Nuevo proyecto</h1>
          <p>Etapa 1 del flujo end-to-end: cliente, país, ubicación, idioma y moneda.</p>
        </div>
      </div>

      <form className="card" onSubmit={handleSubmit} style={{ maxWidth: 640 }}>
        {error && <div className="inline-error">{error}</div>}

        <div className="form-grid">
          <label className="form-field" style={{ gridColumn: "span 2" }}>
            Nombre del proyecto
            <input
              value={form.name}
              onChange={(e) => update("name", e.target.value)}
              required
              maxLength={180}
            />
          </label>

          <label className="form-field">
            País (ISO 3166-1 alpha-2)
            <input
              value={form.country}
              onChange={(e) => update("country", e.target.value)}
              required
              maxLength={2}
              minLength={2}
              placeholder="ES"
            />
          </label>

          <label className="form-field">
            Idioma
            <select value={form.language} onChange={(e) => update("language", e.target.value)}>
              {LANGUAGES.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
          </label>

          <label className="form-field">
            Moneda
            <input
              value={form.currency}
              onChange={(e) => update("currency", e.target.value.toUpperCase())}
              maxLength={3}
              minLength={3}
            />
          </label>

          <label className="form-field">
            Región (opcional)
            <input value={form.region ?? ""} onChange={(e) => update("region", e.target.value)} />
          </label>

          <label className="form-field" style={{ gridColumn: "span 2" }}>
            Descripción (opcional)
            <textarea
              rows={3}
              value={form.description ?? ""}
              onChange={(e) => update("description", e.target.value)}
            />
          </label>
        </div>

        <div className="form-actions">
          <button type="button" className="btn-secondary" onClick={() => navigate("/proyectos")}>
            Cancelar
          </button>
          <button type="submit" className="btn-primary" disabled={saving}>
            {saving ? "Creando…" : "Crear proyecto"}
          </button>
        </div>
      </form>
    </div>
  );
}
