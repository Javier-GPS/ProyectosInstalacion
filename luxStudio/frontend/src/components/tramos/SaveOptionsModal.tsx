import React from 'react';
import { useI18n } from '../../i18n';

interface SaveOptionsModalProps {
  open: boolean;
  saving?: boolean;
  canSaveAlternative?: boolean;
  onSaveAlternative: () => void;
  onReplaceCurrent: () => void;
  onCancel: () => void;
}

const SaveOptionsModal: React.FC<SaveOptionsModalProps> = ({
  open,
  saving,
  canSaveAlternative = true,
  onSaveAlternative,
  onReplaceCurrent,
  onCancel,
}) => {
  const { t } = useI18n();
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 px-4">
      <div className="w-full max-w-md rounded-2xl bg-[#FFFFFF] shadow-2xl">
        <div className="border-b border-[#E8E2D8] px-6 py-4">
          <h2 className="text-base font-semibold text-[#1E1E1E]">{t('saveOptions.title')}</h2>
        </div>
        <div className="px-6 py-4 text-sm text-[#6A6A6A]">
          {t('saveOptions.body')}
        </div>
        <div className="flex flex-col gap-2 border-t border-[#E8E2D8] px-6 py-4">
          <button
            type="button"
            onClick={onReplaceCurrent}
            disabled={saving}
            className="flex w-full items-start gap-3 rounded-lg border border-blue-200 bg-[#FFFFFF] px-4 py-3 text-left transition-colors hover:bg-[#1E1E1E]/6 disabled:opacity-50"
          >
            <svg
              className="mt-0.5 h-5 w-5 flex-shrink-0 text-[#1E1E1E]"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M21 12a9 9 0 1 1-3-6.7" />
              <polyline points="21 4 21 10 15 10" />
            </svg>
            <span className="flex-1">
              <span className="block text-sm font-semibold text-[#333333]">
                {t('saveOptions.replaceCurrent')}
              </span>
              <span className="mt-0.5 block text-xs text-[#A09A91]">
                {t('saveOptions.replaceCurrentHint')}
              </span>
            </span>
          </button>
          {canSaveAlternative && (
            <button
              type="button"
              onClick={onSaveAlternative}
              disabled={saving}
              className="flex w-full items-start gap-3 rounded-lg border border-[#E8E2D8] bg-[#FFFFFF] px-4 py-3 text-left transition-colors hover:bg-[#F7F4EF] disabled:opacity-50"
            >
              <svg
                className="mt-0.5 h-5 w-5 flex-shrink-0 text-[#6A6A6A]"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <rect x="3" y="3" width="7" height="7" rx="1" />
                <rect x="14" y="3" width="7" height="7" rx="1" />
                <rect x="3" y="14" width="7" height="7" rx="1" />
                <rect x="14" y="14" width="7" height="7" rx="1" />
              </svg>
              <span className="flex-1">
                <span className="block text-sm font-semibold text-[#6A6A6A]">
                  {t('saveOptions.saveAlternative')}
                </span>
                <span className="mt-0.5 block text-xs text-[#A09A91]">
                  {t('saveOptions.saveAlternativeHint')}
                </span>
              </span>
            </button>
          )}
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-[#E8E2D8] px-6 py-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={saving}
            className="rounded-lg border border-[#E8E2D8] px-3 py-2 text-sm font-semibold text-[#6A6A6A] hover:bg-[#F7F4EF] disabled:opacity-50"
          >
            {t('saveOptions.cancel')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default SaveOptionsModal;
