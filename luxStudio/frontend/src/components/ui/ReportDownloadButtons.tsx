import React from 'react';
import { useI18n } from '../../i18n';

interface ReportDownloadButtonsProps {
  pdfLoading: boolean;
  excelLoading: boolean;
  disabled: boolean;
  onDownload: (format: 'pdf' | 'excel') => void;
}

const ReportDownloadButtons: React.FC<ReportDownloadButtonsProps> = ({
  pdfLoading,
  excelLoading,
  disabled,
  onDownload,
}) => {
  const { t } = useI18n();
  const busy = pdfLoading || excelLoading;

  const baseClass = `inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-semibold transition-colors`;
  const idleClass = 'border-[#E8E2D8] bg-[#FFFFFF] text-[#6A6A6A] hover:bg-[#F7F4EF]';
  const busyClass = busy
    ? 'cursor-not-allowed border-[#E8E2D8] bg-[#F0EDE8] text-[#6a6a6a]'
    : '';
  const disabledClass = !busy && disabled
    ? 'cursor-not-allowed border-red-200 bg-red-50 text-red-300 line-through decoration-red-300 opacity-60'
    : '';

  return (
    <>
      <button
        type="button"
        onClick={() => onDownload('pdf')}
        disabled={disabled || busy}
        title={disabled ? t('results.calculateFirstForDocuments') : t('tramos.reports.pdf')}
        className={`${baseClass} ${busyClass || disabledClass || idleClass}`}
      >
        {pdfLoading ? (
          <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" opacity="0.25" />
            <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
          </svg>
        ) : (
          <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
            <polyline points="7 10 12 15 17 10" />
            <line x1="12" y1="15" x2="12" y2="3" />
          </svg>
        )}
        <span className={disabled && !busy ? 'line-through decoration-red-300' : ''}>PDF</span>
      </button>
      <button
        type="button"
        onClick={() => onDownload('excel')}
        disabled={disabled || busy}
        title={disabled ? t('results.calculateFirstForDocuments') : t('tramos.reports.excel')}
        className={`${baseClass} ${busyClass || disabledClass || idleClass}`}
      >
        {excelLoading ? (
          <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" opacity="0.25" />
            <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
          </svg>
        ) : (
          <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <path d="M8 13h8M8 17h8M8 9h2" />
          </svg>
        )}
        <span className={disabled && !busy ? 'line-through decoration-red-300' : ''}>Excel</span>
      </button>
    </>
  );
};

export default ReportDownloadButtons;
