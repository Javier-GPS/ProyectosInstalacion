import React from 'react';
import { useI18n } from '../../i18n';

interface NewProjectCardProps {
  onClick: () => void;
}

const NewProjectCard: React.FC<NewProjectCardProps> = ({ onClick }) => {
  const { t } = useI18n();
  return (
    <button
      type="button"
      onClick={onClick}
      className="dashed-border-spaced group flex w-full flex-col items-center justify-center gap-2.5 p-4 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md"
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#1E1E1E]/6 text-[#1E1E1E] transition-colors group-hover:bg-[#1E1E1E] group-hover:text-white">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
      </div>
      <div className="text-center">
        <h3 className="text-sm font-semibold text-[#1E1E1E]">{t('projects.newCard.title')}</h3>
        <p className="mt-0.5 text-xs text-[#A09A91]">{t('projects.newCard.subtitle')}</p>
      </div>
    </button>
  );
};

export default NewProjectCard;
