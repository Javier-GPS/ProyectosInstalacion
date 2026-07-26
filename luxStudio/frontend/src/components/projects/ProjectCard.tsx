import React from 'react';
import { useI18n } from '../../i18n';
import type { ProjectRecord } from '../../lib/projects';

interface ProjectCardProps {
  project: ProjectRecord;
  isOpen: boolean;
  onOpen: (project: ProjectRecord) => void;
  onEdit: (project: ProjectRecord) => void;
  onDelete: (id: number) => void;
}

const formatDate = (iso: string | null | undefined): string => {
  if (!iso) return '-';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleDateString('es', { day: '2-digit', month: 'short', year: 'numeric' });
};

const ProjectCard: React.FC<ProjectCardProps> = ({ project, isOpen, onOpen, onEdit, onDelete }) => {
  const { t } = useI18n();
  const subtitle = [project.client, project.location].filter(Boolean).join(' · ');

  return (
    <article
      className={`group flex flex-col rounded-xl border border-[#E8E2D8] bg-[#FFFFFF] shadow-sm transition-all hover:shadow-md hover:-translate-y-0.5 ${
        isOpen ? 'border-[#4d947d] ring-1 ring-[#1F7A4D]/25' : 'border-[#E8E2D8]'
      }`}
    >
      <div className="flex-1 p-5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <h3 className="truncate text-base font-semibold text-[#1E1E1E]" title={project.project_name}>
              {project.project_name}
            </h3>
            {subtitle && (
              <p className="mt-1 truncate text-sm text-[#A09A91]" title={subtitle}>
                {subtitle}
              </p>
            )}
          </div>
          {isOpen && (
            <span className="shrink-0 inline-flex items-center gap-1 rounded-md bg-[#1F7A4D]/10 px-2 py-0.5 text-xs font-medium text-[#1F7A4D]">
              <span className="h-1.5 w-1.5 rounded-full bg-[#1F7A4D]" />
              {t('projects.card.openBadge')}
            </span>
          )}
        </div>

        <dl className="mt-4 space-y-2 text-xs text-[#A09A91]">
          <div className="flex items-center justify-between">
            <dt>{t('projects.card.studyDate')}</dt>
            <dd className="font-medium text-[#6A6A6A]">{formatDate(project.study_date)}</dd>
          </div>
          <div className="flex items-center justify-between">
            <dt>{t('projects.card.lastOpened')}</dt>
            <dd className="font-medium text-[#6A6A6A]">{formatDate(project.last_opened_at)}</dd>
          </div>
          {project.standard && (
            <div className="flex items-center justify-between">
              <dt>{t('projects.card.standard')}</dt>
              <dd className="font-medium text-[#6A6A6A]">{project.standard}</dd>
            </div>
          )}
        </dl>
      </div>

      <div className="flex items-center gap-2 border-t border-[#E8E2D8] bg-[#FCF9F5]/40 px-5 py-3">
        <button
          type="button"
          onClick={() => onOpen(project)}
          className="flex-1 rounded-lg bg-[#1E1E1E] px-3 py-2 text-sm font-semibold text-white transition-colors hover:bg-[#333333]"
        >
          {t('projects.card.actions.open')}
        </button>
        <button
          type="button"
          onClick={() => onEdit(project)}
          className="rounded-lg border border-[#E8E2D8] px-3 py-2 text-sm font-semibold text-[#6A6A6A] transition-colors hover:bg-[#F7F4EF]"
          title={t('projects.card.actions.edit')}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
          </svg>
        </button>
        <button
          type="button"
          onClick={() => onDelete(project.id)}
          className="rounded-lg border border-[#B42318]/25 px-3 py-2 text-sm font-semibold text-[#B42318] transition-colors hover:bg-[#FDECEA]"
          title={t('projects.card.actions.delete')}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
            <path d="M10 11v6M14 11v6" />
            <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
          </svg>
        </button>
      </div>
    </article>
  );
};

export default ProjectCard;
