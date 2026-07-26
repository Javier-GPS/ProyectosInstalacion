import React from 'react';
import { useI18n } from '../../i18n';

interface UnsavedChangesModalProps {
  open: boolean;
  onSaveAndExit: () => void;
  onReplaceAndExit?: () => void;
  onSaveAlternativeAndExit?: () => void;
  onDiscard: () => void;
  onCancel: () => void;
  saving?: boolean;
  calculated?: boolean;
  pendingSaveOnly?: boolean;
  canSaveAlternative?: boolean;
}

const UnsavedChangesModal: React.FC<UnsavedChangesModalProps> = ({
  open,
  onSaveAndExit,
  onReplaceAndExit,
  onSaveAlternativeAndExit,
  onDiscard,
  onCancel,
  saving,
  calculated,
  pendingSaveOnly,
  canSaveAlternative = true,
}) => {
  const { t } = useI18n();
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 px-4">
      <div className="w-full max-w-md rounded-2xl bg-[#FFFFFF] shadow-2xl">
        <div className="border-b border-[#E8E2D8] px-6 py-4">
          <h2 className="text-base font-semibold text-[#1E1E1E]">{t(pendingSaveOnly ? 'unsavedChanges.pendingSaveTitle' : calculated ? 'unsavedChanges.calculatedTitle' : 'unsavedChanges.title')}</h2>
        </div>
        <div className="px-6 py-4 text-sm text-[#6A6A6A]">
          {t(pendingSaveOnly ? 'unsavedChanges.pendingSaveBody' : calculated ? 'unsavedChanges.calculatedBody' : 'unsavedChanges.body')}
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-[#E8E2D8] px-6 py-3">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-[#E8E2D8] px-3 py-2 text-sm font-semibold text-[#6A6A6A] hover:bg-[#F7F4EF]"
          >
            {t('unsavedChanges.cancel')}
          </button>
          <button
            type="button"
            onClick={onDiscard}
            className="rounded-lg border border-[#B42318]/25 bg-[#FFFFFF] px-3 py-2 text-sm font-semibold text-[#B42318] hover:bg-[#FDECEA]"
          >
            {t('unsavedChanges.discard')}
          </button>
          {pendingSaveOnly ? (
            <button type="button" onClick={onSaveAndExit} disabled={saving} className="rounded-lg bg-[#1E1E1E] px-3 py-2 text-sm font-semibold text-white hover:bg-[#333333] disabled:opacity-50">
              {saving ? t('form.saving') : t('unsavedChanges.saveAndExit')}
            </button>
          ) : calculated ? (
            <>
              <button type="button" onClick={onReplaceAndExit} disabled={saving} className="rounded-lg bg-[#1E1E1E] px-3 py-2 text-sm font-semibold text-white hover:bg-[#333333] disabled:opacity-50">
                {saving ? t('form.saving') : t('unsavedChanges.replaceCurrent')}
              </button>
              {canSaveAlternative && (
                <button type="button" onClick={onSaveAlternativeAndExit} disabled={saving} className="rounded-lg border border-[#1E1E1E]/15 bg-[#FFFFFF] px-3 py-2 text-sm font-semibold text-[#333333] hover:bg-[#1E1E1E]/6 disabled:opacity-50">
                  {t('unsavedChanges.saveAlternative')}
                </button>
              )}
            </>
          ) : (
            <button type="button" onClick={onSaveAndExit} disabled={saving} className={`rounded-lg px-3 py-2 text-sm font-semibold text-white ${saving ? 'bg-[#1E1E1E]/50 cursor-not-allowed' : 'bg-[#1E1E1E] hover:bg-[#333333]'}`}>
              {saving ? t('actions.calculating') : t('unsavedChanges.calculateNow')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default UnsavedChangesModal;
