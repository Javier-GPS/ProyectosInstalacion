import { useCallback, useState } from 'react';
import { useConfigStore } from '../store/useConfigStore';
import { useAuth } from '../auth/AuthContext';
import { useI18n } from '../i18n';
import type { CalculationResult } from '../types';
import { buildReportRequestBody } from '../lib/reportRequest';
import { triggerDownload } from '../lib/download';

export interface UseReportDownloadOptions {
  result: CalculationResult | null | undefined;
  configOverride?: any;
  tramoId?: number;
  needsCalculation?: boolean;
  onDocumentSaved?: () => void;
}

export const useReportDownload = ({
  result,
  configOverride,
  tramoId,
  needsCalculation,
  onDocumentSaved,
}: UseReportDownloadOptions) => {
  const { authFetch } = useAuth();
  const { t } = useI18n();
  const [pdfLoading, setPdfLoading] = useState(false);
  const [excelLoading, setExcelLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDownload = useCallback(
    async (format: 'pdf' | 'excel') => {
      if (!result || !result.luminaire || !Array.isArray(result.criteria)) return;
      if (needsCalculation) {
        setError(t('results.calculateFirstForDocuments'));
        return;
      }
      const isPdf = format === 'pdf';
      isPdf ? setPdfLoading(true) : setExcelLoading(true);
      setError(null);

      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 60000);

        const endpoint = isPdf ? '/api/report/generate' : '/api/report/excel';
        const requestUrl = tramoId ? `${endpoint}?tramo_id=${tramoId}` : endpoint;
        const config = useConfigStore.getState();
        const response = await authFetch(requestUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(buildReportRequestBody(config, configOverride)),
          signal: controller.signal,
        });
        clearTimeout(timeout);

        if (!response.ok) {
          const errData = await response.json().catch(() => null);
          throw new Error(errData?.detail || t('errors.server', { status: response.status }));
        }

        const blob = await response.blob();
        triggerDownload(blob, `${isPdf ? 'LUX_Report' : 'LUX_Results'}_${result.luminaire.luminaire_name.replace(/\s+/g, '_')}.${isPdf ? 'pdf' : 'xlsx'}`);
        onDocumentSaved?.();
      } catch (err: any) {
        if (err.name === 'AbortError') {
          setError(t('results.timeout', { type: isPdf ? 'PDF' : 'Excel' }));
        } else {
          setError(err.message || t('results.failedGenerate', { type: isPdf ? 'PDF' : 'Excel' }));
        }
      } finally {
        isPdf ? setPdfLoading(false) : setExcelLoading(false);
      }
    },
    [result, configOverride, tramoId, needsCalculation, onDocumentSaved, authFetch, t],
  );

  const disabled = !result || !result.luminaire || !Array.isArray(result.criteria) || !!needsCalculation;

  return {
    pdfLoading,
    excelLoading,
    error,
    handleDownload,
    disabled,
  };
};
