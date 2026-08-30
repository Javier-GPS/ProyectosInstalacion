import React, { useEffect, useState } from 'react';
import { useI18n } from '../../i18n';
import type { GisProject } from '../../types';
import { createProject, updateProject } from '../../lib/api';

export interface ProjectFormValue {
  project_name: string;
  client: string;
  location: string;
  designer: string;
  study_date: string;
  reference: string;
  calculation_type: string;
  standard: string;
  notes: string;
}

const emptyValue = (): ProjectFormValue => ({
  project_name: '',
  client: '',
  location: '',
  designer: '',
  study_date: new Date().toISOString().slice(0, 10),
  reference: '',
  calculation_type: '',
  standard: 'EN 13201:2015',
  notes: '',
});

const fromProject = (project: GisProject): ProjectFormValue => ({
  project_name: project.project_name ?? project.name ?? '',
  client: project.client ?? '',
  location: project.location ?? '',
  designer: project.designer ?? '',
  study_date: project.study_date ?? new Date().toISOString().slice(0, 10),
  reference: project.reference ?? '',
  calculation_type: project.calculation_type ?? '',
  standard: project.standard ?? 'EN 13201:2015',
  notes: project.notes ?? '',
});

const fields: Array<{ key: keyof ProjectFormValue; labelKey: string; placeholderKey: string; type?: string; textarea?: boolean }> = [
  { key: 'project_name', labelKey: 'projects.form.name', placeholderKey: 'projects.form.name' },
  { key: 'client', labelKey: 'projects.form.client', placeholderKey: 'projects.form.client' },
  { key: 'location', labelKey: 'projects.form.location', placeholderKey: 'projects.form.location' },
  { key: 'designer', labelKey: 'projects.form.designer', placeholderKey: 'projects.form.designer' },
  { key: 'study_date', labelKey: 'projects.form.studyDate', placeholderKey: 'projects.form.studyDate', type: 'date' },
  { key: 'reference', labelKey: 'projects.form.reference', placeholderKey: 'projects.form.reference' },
  { key: 'calculation_type', labelKey: 'projects.form.calculationType', placeholderKey: 'projects.form.calculationType' },
  { key: 'standard', labelKey: 'projects.form.standard', placeholderKey: 'projects.form.standard' },
  { key: 'notes', labelKey: 'projects.form.notes', placeholderKey: 'projects.form.notes', textarea: true },
];

interface ProjectFormModalProps {
  open: boolean;
  onClose: () => void;
  onSaved: (project: GisProject) => void;
  initialProject?: GisProject | null;
}

const ProjectFormModal: React.FC<ProjectFormModalProps> = ({ open, onClose, onSaved, initialProject }) => {
  const { t } = useI18n();
  const [value, setValue] = useState<ProjectFormValue>(emptyValue());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setValue(initialProject ? fromProject(initialProject) : emptyValue());
    setError(null);
  }, [open, initialProject]);

  if (!open) return null;

  const update = (key: keyof ProjectFormValue, val: string) => {
    setValue(current => ({ ...current, [key]: val }));
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const body = { ...value, status: 'draft' };
      const saved = initialProject?.id
        ? await updateProject(initialProject.id, body)
        : await createProject(body);
      onSaved(saved);
      onClose();
    } catch (err: any) {
      setError(err.message || t('projects.form.error'));
    } finally {
      setSaving(false);
    }
  };

  const isEdit = Boolean(initialProject?.id);
  const disabled = saving || value.project_name.trim().length === 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 px-4 py-8">
      <div className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl bg-[#F7F4EF] border border-[#E8E2D8] shadow-2xl">
        <div className="flex items-center justify-between border-b border-[#E8E2D8] px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold text-[#1E1E1E]">
              {isEdit ? t('projects.form.title.edit') : t('projects.form.title.new')}
            </h2>
            <p className="text-xs text-[#A09A91] mt-0.5">
              {initialProject ? `#${initialProject.id}` : ''}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-[#6a6a6a] hover:bg-[#FFFFFF] hover:text-[#6A6A6A]"
            aria-label="Cerrar"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {fields.map(field => (
              <label
                key={field.key}
                className={`text-sm font-semibold text-[#6A6A6A] ${field.textarea ? 'md:col-span-2' : ''}`}
              >
                {t(field.labelKey)}
                {field.textarea ? (
                  <textarea
                    value={value[field.key]}
                    onChange={event => update(field.key, event.target.value)}
                    placeholder={t(field.placeholderKey)}
                    rows={3}
                    className="mt-1 w-full rounded-lg border border-[#E8E2D8] bg-[#FFFFFF] px-3 py-2 text-sm font-normal outline-none focus:border-[#1E1E1E] focus:ring-2 focus:ring-[#1E1E1E]/10 text-[#1E1E1E]"
                  />
                ) : (
                  <input
                    type={field.type ?? 'text'}
                    value={value[field.key]}
                    onChange={event => update(field.key, event.target.value)}
                    placeholder={t(field.placeholderKey)}
                    required={field.key === 'project_name'}
                    className="mt-1 w-full rounded-lg border border-[#E8E2D8] bg-[#FFFFFF] px-3 py-2 text-sm font-normal outline-none focus:border-[#1E1E1E] focus:ring-2 focus:ring-[#1E1E1E]/10 text-[#1E1E1E]"
                  />
                )}
              </label>
            ))}
          </div>
          {error && (
            <div className="rounded-lg border border-[#B42318]/25 bg-[#FDECEA] px-3 py-2 text-sm text-[#B42318]">
              {error}
            </div>
          )}
          <div className="flex items-center justify-end gap-3 border-t border-[#E8E2D8] pt-4">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-[#E8E2D8] px-4 py-2 text-sm font-semibold text-[#6A6A6A] hover:bg-[#FFFFFF]"
            >
              {t('projects.form.cancel')}
            </button>
            <button
              type="submit"
              disabled={disabled}
              className={`rounded-lg px-4 py-2 text-sm font-semibold text-[#1E1E1E] ${
                disabled ? 'bg-[#1E1E1E]/50 cursor-not-allowed' : 'bg-[#1E1E1E] hover:bg-[#333333]'
              }`}
            >
              {saving ? t('actions.loading') : t('projects.form.save')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default ProjectFormModal;
