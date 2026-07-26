import React from 'react';
import { CheckCircle2, XCircle, X, Save, Replace, Zap } from 'lucide-react';
import { useI18n } from '../../i18n';
import type { OptimizationLensResult } from '../../types';

interface AdvancedOptimizationResultsModalProps {
  open: boolean;
  rows: OptimizationLensResult[];
  saving?: boolean;
  canSaveAlternative?: boolean;
  onSaveAlternative: (row: OptimizationLensResult) => void;
  onReplaceCurrent: (row: OptimizationLensResult) => void;
  onClose: () => void;
}

const valueNumber = (value: unknown): number | null => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const rowPower = (row: OptimizationLensResult): number | null => (
  valueNumber(row.config?.power) ?? valueNumber(row.result?.luminaire?.power)
);

const metricValue = (row: OptimizationLensResult, key: string): string => {
  const value = valueNumber(row.config?.[key] ?? row.result?.config?.[key]);
  if (value === null) return '-';
  if (key === 'tilt') return `${value.toFixed(0)} deg`;
  return `${value.toFixed(1)} m`;
};

const AdvancedOptimizationResultsModal: React.FC<AdvancedOptimizationResultsModalProps> = ({
  open,
  rows,
  saving,
  canSaveAlternative = true,
  onSaveAlternative,
  onReplaceCurrent,
  onClose,
}) => {
  const { t } = useI18n();
  if (!open) return null;

  const feasibleRows = rows.filter(row => row.feasible && row.result && row.config);
  const lowestPower = feasibleRows.reduce<number | null>((lowest, row) => {
    const power = rowPower(row);
    if (power === null) return lowest;
    return lowest === null || power < lowest ? power : lowest;
  }, null);
  const compliantCount = feasibleRows.length;
  const nonCompliantCount = rows.length - compliantCount;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 px-3 py-4">
      <div className="flex max-h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl bg-[#FFFFFF] shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-[#E8E2D8] px-5 py-4">
          <div className="min-w-0">
            <h2 className="text-base font-bold text-[#1E1E1E]">{t('advancedResults.title')}</h2>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs font-semibold">
              <span className="inline-flex items-center gap-1 rounded-full border border-[#1F7A4D]/25 bg-[#1F7A4D]/10 px-2.5 py-1 text-[#1F7A4D]">
                <CheckCircle2 className="h-3.5 w-3.5" />
                {t('advancedResults.compliantCount', { count: compliantCount })}
              </span>
              <span className="inline-flex items-center gap-1 rounded-full border border-[#B42318]/25 bg-[#FDECEA] px-2.5 py-1 text-[#B42318]">
                <XCircle className="h-3.5 w-3.5" />
                {t('advancedResults.nonCompliantCount', { count: nonCompliantCount })}
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="rounded-lg border border-[#E8E2D8] p-2 text-[#A09A91] hover:bg-[#F7F4EF] disabled:opacity-50"
            aria-label={t('advancedResults.close')}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto bg-[#FCF9F5]/70 px-5 py-4">
          <div className="space-y-3">
            {rows.map(row => {
              const power = rowPower(row);
              const isLowest = row.feasible && power !== null && lowestPower !== null && Math.abs(power - lowestPower) < 0.001;
              const canUse = row.feasible && Boolean(row.config && row.result);

              return (
                <article
                  key={row.model_id}
                  className={`overflow-hidden rounded-xl border bg-[#FFFFFF] shadow-sm ${
                    row.feasible ? 'border-[#1F7A4D]/25' : 'border-[#B42318]/25'
                  }`}
                >
                  <div className="grid gap-3 p-3 sm:grid-cols-[9rem_minmax(0,1fr)_auto] sm:items-center">
                    <div className={`flex h-full min-h-[5.5rem] flex-col justify-center rounded-xl border px-3 py-2 ${
                      isLowest
                        ? 'border-emerald-300 bg-[#1F7A4D]/100 text-white shadow-sm'
                        : row.feasible
                          ? 'border-[#1F7A4D]/25 bg-[#1F7A4D]/10 text-emerald-800'
                          : 'border-[#E8E2D8] bg-[#FCF9F5] text-[#A09A91]'
                    }`}>
                      <div className="flex items-center gap-1 text-[10px] font-bold uppercase">
                        <Zap className="h-3.5 w-3.5" />
                        {t('luminaire.power')}
                      </div>
                      <div className="mt-1 text-2xl font-black tracking-tight">
                        {power !== null ? power.toFixed(1) : '-'}
                      </div>
                      <div className="text-xs font-bold">W</div>
                      {isLowest && (
                        <div className="mt-1 text-[10px] font-bold uppercase">
                          {t('advancedResults.lowestPower')}
                        </div>
                      )}
                    </div>

                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-bold ${
                          row.feasible ? 'bg-[#1F7A4D]/10 text-[#1F7A4D]' : 'bg-[#FDECEA] text-[#B42318]'
                        }`}>
                          {row.feasible ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
                          {row.feasible ? t('results.compliant') : t('results.nonCompliant')}
                        </span>
                        <h3 className="min-w-0 truncate text-sm font-bold text-[#1E1E1E]" title={row.model_id}>
                          {row.optic_family}
                        </h3>
                      </div>

                      <div className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
                        <div className="rounded-lg bg-[#FCF9F5] px-2.5 py-2">
                          <div className="font-semibold text-[#6a6a6a]">{t('geometry.spacing')}</div>
                          <div className="mt-0.5 font-bold text-[#6A6A6A]">{metricValue(row, 'spacing')}</div>
                        </div>
                        <div className="rounded-lg bg-[#FCF9F5] px-2.5 py-2">
                          <div className="font-semibold text-[#6a6a6a]">{t('pole.height')}</div>
                          <div className="mt-0.5 font-bold text-[#6A6A6A]">{metricValue(row, 'height')}</div>
                        </div>
                        <div className="rounded-lg bg-[#FCF9F5] px-2.5 py-2">
                          <div className="font-semibold text-[#6a6a6a]">{t('pole.armLength')}</div>
                          <div className="mt-0.5 font-bold text-[#6A6A6A]">{metricValue(row, 'arm_length')}</div>
                        </div>
                        <div className="rounded-lg bg-[#FCF9F5] px-2.5 py-2">
                          <div className="font-semibold text-[#6a6a6a]">{t('pole.armTilt')}</div>
                          <div className="mt-0.5 font-bold text-[#6A6A6A]">{metricValue(row, 'tilt')}</div>
                        </div>
                      </div>

                      {!row.feasible && row.message && (
                        <p className="mt-2 text-xs leading-relaxed text-[#B42318]">{row.message}</p>
                      )}
                    </div>

                    <div className="flex flex-col gap-2 sm:w-44">
                      <button
                        type="button"
                        onClick={() => onReplaceCurrent(row)}
                        disabled={!canUse || saving}
                        className="inline-flex items-center justify-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-xs font-bold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
                      >
                        <Replace className="h-3.5 w-3.5" />
                        {t('advancedResults.replaceCurrent')}
                      </button>
                      {canSaveAlternative && (
                        <button
                          type="button"
                          onClick={() => onSaveAlternative(row)}
                          disabled={!canUse || saving}
                          className="inline-flex items-center justify-center gap-2 rounded-lg border border-blue-200 bg-[#FFFFFF] px-3 py-2 text-xs font-bold text-[#333333] hover:bg-[#1E1E1E]/6 disabled:cursor-not-allowed disabled:opacity-45"
                        >
                          <Save className="h-3.5 w-3.5" />
                          {t('advancedResults.saveAlternative')}
                        </button>
                      )}
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        </div>

        <div className="flex items-center justify-end border-t border-[#E8E2D8] px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="rounded-lg border border-[#E8E2D8] bg-[#FFFFFF] px-4 py-2 text-sm font-semibold text-[#6A6A6A] hover:bg-[#F7F4EF] disabled:opacity-50"
          >
            {t('advancedResults.closeNoSave')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default AdvancedOptimizationResultsModal;
