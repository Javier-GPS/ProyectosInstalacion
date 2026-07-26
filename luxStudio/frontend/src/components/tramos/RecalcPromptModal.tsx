import React from 'react';
import { useI18n } from '../../i18n';

interface RecalcPromptModalProps {
  open: boolean;
  onSaveAnyway: () => void;
  onCalculateFirst: () => void;
  onCancel: () => void;
}

const RecalcPromptModal: React.FC<RecalcPromptModalProps> = ({
  open,
  onSaveAnyway,
  onCalculateFirst,
  onCancel,
}) => {
  const { t } = useI18n();
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 px-4">
      <div className="w-full max-w-md rounded-2xl bg-[#FFFFFF] shadow-2xl">
        <div className="border-b border-[#E8E2D8] px-6 py-4">
          <h2 className="text-base font-semibold text-[#1E1E1E]">{t('unsavedChanges.recalc.title')}</h2>
        </div>
        <div className="px-6 py-4 text-sm text-[#6A6A6A]">
          {t('unsavedChanges.recalc.body')}
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-[#E8E2D8] px-6 py-3">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-[#E8E2D8] px-3 py-2 text-sm font-semibold text-[#6A6A6A] hover:bg-[#F7F4EF]"
          >
            {t('unsavedChanges.recalc.cancel')}
          </button>
          <button
            type="button"
            onClick={onCalculateFirst}
            className="rounded-lg border border-blue-200 bg-[#FFFFFF] px-3 py-2 text-sm font-semibold text-[#1E1E1E] hover:bg-[#1E1E1E]/6"
          >
            {t('unsavedChanges.recalc.calculateFirst')}
          </button>
          <button
            type="button"
            onClick={onSaveAnyway}
            className="rounded-lg bg-[#1E1E1E] px-3 py-2 text-sm font-semibold text-white hover:bg-[#333333]"
          >
            {t('unsavedChanges.recalc.saveAnyway')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default RecalcPromptModal;
