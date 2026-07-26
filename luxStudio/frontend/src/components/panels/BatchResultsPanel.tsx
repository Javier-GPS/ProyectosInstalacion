import React, { useMemo, useState } from 'react';
import type { BatchCalculationItem, BatchCalculationResponse } from '../../types';
import { useConfigStore } from '../../store/useConfigStore';
import { useI18n } from '../../i18n';
import { useColumnFilters, type ColumnFilterDef } from '../../hooks/useColumnFilters';
import { triggerDownload } from '../../lib/download';

interface BatchResultsPanelProps {
  batch: BatchCalculationResponse;
}

const metricText = (item: BatchCalculationItem) => {
  const result = item.result;
  if (!result) return '-';
  if (result.mode === 'P') {
    return `Eavg ${result.Eavg?.toFixed(2) ?? '-'} / Emin ${result.Emin?.toFixed(2) ?? '-'}`;
  }
  return `Lavg ${result.Lavg?.toFixed(2) ?? '-'} / Uo ${result.Uo?.toFixed(2) ?? '-'}`;
};

const BatchResultsPanel: React.FC<BatchResultsPanelProps> = ({ batch }) => {
  const { t } = useI18n();
  const language = useConfigStore(state => state.language);
  const [loadingKey, setLoadingKey] = useState<string | null>(null);
  const successful = batch.items.filter(item => item.result && item.config);
  const failed = batch.items.filter(item => item.error);
  const passCount = successful.filter(item => item.result?.compliant).length;
  const failCount = successful.length - passCount;

  const filterDefs: ColumnFilterDef<BatchCalculationItem>[] = useMemo(() => [
    { key: 'model', getValue: item => item.model_id },
    { key: 'setup', getValue: item => `${item.config?.arrangement} h${item.config?.height} S${item.config?.spacing}` },
    { key: 'luminaire', getValue: item => item.result?.luminaire.luminaire_name || '' },
    { key: 'result', getValue: item => {
      const r = item.result;
      if (!r) return '';
      if (r.mode === 'P') return `Eavg ${r.Eavg} Emin ${r.Emin}`;
      return `Lavg ${r.Lavg} Uo ${r.Uo}`;
    }},
    { key: 'status', getValue: item => item.result?.compliant ? 'pass' : 'fail' },
  ], []);

  const { filters, setFilter, filteredData } = useColumnFilters(successful, filterDefs);

  const downloadOutput = async (item: BatchCalculationItem, format: 'pdf' | 'excel') => {
    if (!item.config || !item.result) return;
    const key = `${item.row}-${format}`;
    setLoadingKey(key);
    try {
      const response = await fetch(format === 'pdf' ? '/api/report/generate' : '/api/report/excel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...item.config, language }),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => null);
        throw new Error(errData?.detail || t('errors.server', { status: response.status }));
      }

      const blob = await response.blob();
      triggerDownload(blob, `${format === 'pdf' ? 'LUX_Report' : 'LUX_Results'}_${item.model_id.replace(/\s+/g, '_')}.${format === 'pdf' ? 'pdf' : 'xlsx'}`);
    } finally {
      setLoadingKey(null);
    }
  };

  return (
    <div className="bg-[#FFFFFF] rounded-xl border border-[#E8E2D8] shadow-sm overflow-hidden">
      <div className="px-4 py-3 bg-[#FCF9F5] border-b border-[#E8E2D8] flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-[#6A6A6A] text-sm">{t('batch.results')}</h3>
          <p className="text-xs text-[#6a6a6a] mt-0.5">{batch.filename}</p>
        </div>
        <span className="text-xs text-[#A09A91]">{t('batch.summary', { ok: successful.length, errors: failed.length })}</span>
      </div>

      {failed.length > 0 && (
        <div className="p-3 border-b border-[#E8E2D8] space-y-2">
          {failed.slice(0, 5).map(item => (
            <div key={`${item.row}-${item.model_id}`} className="text-xs text-[#B42318] bg-[#FDECEA] border border-[#B42318]/25 rounded-lg p-2">
              {t('batch.rowError', { row: item.row, model: item.model_id, error: item.error || '' })}
            </div>
          ))}
        </div>
      )}

      <div className="px-4 py-2 border-b border-[#E8E2D8] bg-[#FFFFFF] flex items-center justify-between">
        <span className="text-xs text-[#6a6a6a]">
          Mostrando {filteredData.length} / {successful.length} resultados · {passCount} pass / {failCount} fail
        </span>
      </div>

      <div className="max-h-[620px] overflow-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 z-10">
            <tr className="bg-[#F0EDE8] text-[#6A6A6A]">
              <th className="text-left font-semibold px-3 py-2">{t('batch.model')}</th>
              <th className="text-left font-semibold px-3 py-2">{t('batch.setup')}</th>
              <th className="text-left font-semibold px-3 py-2">{t('results.luminaire')}</th>
              <th className="text-left font-semibold px-3 py-2">{t('batch.result')}</th>
              <th className="text-left font-semibold px-3 py-2">{t('batch.status')}</th>
              <th className="text-right font-semibold px-3 py-2">{t('batch.outputs')}</th>
            </tr>
            <tr className="bg-[#FFFFFF] border-b border-[#E8E2D8]">
              <th className="px-1 py-1"><input value={filters.model || ''} onChange={e => setFilter('model', e.target.value)} placeholder="Modelo" className="w-full px-1.5 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-blue-400" /></th>
              <th className="px-1 py-1"><input value={filters.setup || ''} onChange={e => setFilter('setup', e.target.value)} placeholder="Setup" className="w-full px-1.5 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-blue-400" /></th>
              <th className="px-1 py-1"><input value={filters.luminaire || ''} onChange={e => setFilter('luminaire', e.target.value)} placeholder="Luminaria" className="w-full px-1.5 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-blue-400" /></th>
              <th className="px-1 py-1"><input value={filters.result || ''} onChange={e => setFilter('result', e.target.value)} placeholder="Resultado" className="w-full px-1.5 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-blue-400" /></th>
              <th className="px-1 py-1"><input value={filters.status || ''} onChange={e => setFilter('status', e.target.value)} placeholder="Estado" className="w-full px-1.5 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-blue-400" /></th>
              <th className="px-1 py-1" />
            </tr>
          </thead>
          <tbody>
            {filteredData.map(item => (
              <tr key={`${item.row}-${item.model_id}`} className="border-t border-[#E8E2D8] hover:bg-[#F7F4EF]">
                <td className="px-3 py-2 font-medium text-[#6A6A6A]">{item.model_id}</td>
                <td className="px-3 py-2 text-[#A09A91]">
                  {item.config?.arrangement} - h {item.config?.height} - S {item.config?.spacing}
                </td>
                <td className="px-3 py-2 text-[#A09A91]">{item.result?.luminaire.luminaire_name}</td>
                <td className="px-3 py-2 text-[#A09A91]">{metricText(item)}</td>
                <td className="px-3 py-2">
                  <span className={`font-bold ${item.result?.compliant ? 'text-green-600' : 'text-[#B42318]'}`}>
                    {item.result?.compliant ? t('status.pass') : t('status.fail')}
                  </span>
                </td>
                <td className="px-3 py-2">
                  <div className="flex justify-end gap-1.5">
                    <button
                      onClick={() => downloadOutput(item, 'pdf')}
                      disabled={loadingKey !== null}
                      className="px-2 py-1 rounded-md border border-[#E8E2D8] bg-[#FFFFFF] hover:bg-[#FFFFFF] text-[#6A6A6A] disabled:opacity-50"
                    >
                      {loadingKey === `${item.row}-pdf` ? '...' : 'PDF'}
                    </button>
                    <button
                      onClick={() => downloadOutput(item, 'excel')}
                      disabled={loadingKey !== null}
                      className="px-2 py-1 rounded-md border border-[#E8E2D8] bg-[#FFFFFF] hover:bg-[#FFFFFF] text-[#6A6A6A] disabled:opacity-50"
                    >
                      {loadingKey === `${item.row}-excel` ? '...' : 'Excel'}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {filteredData.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-[#6a6a6a]">
                  {t('batch.noMatches')}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default BatchResultsPanel;
