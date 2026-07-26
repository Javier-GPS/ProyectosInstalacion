import React from 'react';
import { useI18n } from '../../i18n';

interface ConfirmModalProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

const ConfirmModal: React.FC<ConfirmModalProps> = ({
  open,
  title,
  message,
  confirmLabel,
  cancelLabel,
  destructive,
  busy,
  onConfirm,
  onCancel,
}) => {
  const { t } = useI18n();
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 px-4">
      <div className="w-full max-w-md rounded-2xl bg-[#FFFFFF] shadow-2xl">
        <div className="border-b border-[#E8E2D8] px-6 py-4">
          <h2 className="text-base font-semibold text-[#1E1E1E]">{title}</h2>
        </div>
        <div className="px-6 py-4 text-sm text-[#6A6A6A]">{message}</div>
        <div className="flex items-center justify-end gap-2 border-t border-[#E8E2D8] px-6 py-3">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-[#E8E2D8] px-3 py-2 text-sm font-semibold text-[#6A6A6A] hover:bg-[#F7F4EF]"
          >
            {cancelLabel ?? t('unsavedChanges.cancel')}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={`rounded-lg px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed ${
              destructive
                ? (busy ? 'bg-red-300' : 'bg-red-600 hover:bg-red-700')
                : (busy ? 'bg-[#1E1E1E]/50' : 'bg-[#1E1E1E] hover:bg-[#333333]')
            }`}
          >
            {busy ? t('actions.calculating') : (confirmLabel ?? t('unsavedChanges.saveAndExit'))}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmModal;
