import React from 'react';
import { useI18n } from '../../i18n';

interface EmptyProjectsStateProps {
  onCreate: () => void;
}

const EmptyProjectsState: React.FC<EmptyProjectsStateProps> = ({ onCreate }) => {
  const { t } = useI18n();
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-[#E8E2D8] bg-[#FFFFFF] px-6 py-16 text-center">
      <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-[#1E1E1E]/6">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="text-[#1E1E1E]">
          <path d="M3 21h18" />
          <path d="M5 21V8l7-5 7 5v13" />
          <path d="M9 21v-6h6v6" />
          <circle cx="12" cy="11" r="1.4" fill="currentColor" />
          <path d="M9.5 9.5 12 7l2.5 2.5" />
        </svg>
      </div>
      <h2 className="text-lg font-semibold text-[#1E1E1E]">{t('projects.empty.title')}</h2>
      <p className="mt-2 max-w-md text-sm text-[#A09A91]">{t('projects.empty.subtitle')}</p>
      <button
        type="button"
        onClick={onCreate}
        className="mt-6 inline-flex items-center gap-2 rounded-lg bg-[#1E1E1E] px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-[#333333]"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
        {t('projects.empty.cta')}
      </button>
    </div>
  );
};

export default EmptyProjectsState;
