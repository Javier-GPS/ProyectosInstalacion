import React, { useState, useCallback, useEffect, useMemo } from 'react';
import { useConfigStore } from '../../store/useConfigStore';
import type { CalculationResult, ElementResultItem } from '../../types';
import { useI18n } from '../../i18n';
import { useReportDownload } from '../../hooks/useReportDownload';
import ReportDownloadButtons from '../ui/ReportDownloadButtons';
import MeasurementsButton from '../ui/MeasurementsButton';
import { buildReportRequestBody } from '../../lib/reportRequest';
import { buildCalculationRequest } from '../../lib/tramoRequest';
import { luminaireLocationLabels, roadElementLabel } from '../../lib/roadGeometry';

interface QuickInfoPanelProps {
  result: CalculationResult | null;
  loading: boolean;
  tramoId?: number;
  projectName?: string;
  needsCalculation?: boolean;
  onDocumentSaved?: () => void;
}

const carriagewayMetrics = [
  { key: 'Lavg', criterion: 'Lavg', label: 'LAVG', unit: 'cd/m²', decimals: 2 },
  { key: 'Uo', criterion: 'Uo', label: 'Uo', unit: '', decimals: 2 },
  { key: 'Ul', criterion: 'Ul', label: 'Ul', unit: '', decimals: 2 },
  { key: 'TI', criterion: 'TI', label: 'TI', unit: '%', decimals: 2 },
  { key: 'SR', criterion: 'SR', label: 'SR', unit: '', decimals: 2 },
  { key: 'EIR', criterion: 'EIR', label: 'EIR', unit: '', decimals: 2 },
] as const;
const sidewalkMetrics = [
  { key: 'Eavg_ped', criterion: 'Eavg', label: 'Eavg', unit: 'lux', decimals: 2 },
  { key: 'Emin_ped', criterion: 'Emin', label: 'Emin', unit: 'lux', decimals: 2 },
] as const;

function MetricBarRow({ label, value, required, passed, decimals, lowerBetter, disabled = false, onClick, title }: {
  label: string; value: number; required?: number; passed: boolean; decimals: number;
  lowerBetter: boolean; disabled?: boolean; onClick?: () => void; title?: string;
}) {
  const ratio = !required || required <= 0 ? 0
    : lowerBetter ? required / Math.max(value, 0.001) : value / required;
  const pct = Math.min(ratio * 100, 100);
  return (
    <div onClick={onClick} title={title}
      className={`flex items-center gap-2 rounded-md px-2 py-1 text-xs ${onClick ? 'cursor-pointer select-none' : ''} ${
        disabled ? 'opacity-35 bg-[#FCF9F5]' : passed ? 'hover:bg-green-50/50' : 'hover:bg-amber-50/50'
      }`}>
      <span className={`w-20 shrink-0 truncate font-semibold ${disabled ? 'text-[#6a6a6a] line-through' : 'text-[#6A6A6A]'}`}>
        {label}
      </span>
      <span className={`w-14 shrink-0 text-right font-mono font-medium ${
        disabled ? 'text-[#6a6a6a]' : passed ? 'text-[#1E1E1E]' : 'text-[#B7791F]'
      }`}>
        {value.toFixed(decimals)}
      </span>
      <div className="h-[5px] min-w-[40px] flex-1 rounded-full bg-[#E8E2D8]">
        <div className={`h-[5px] rounded-full transition-all ${disabled ? 'bg-[#3a4a4d]' : passed ? 'bg-green-400' : 'bg-amber-400'}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-14 shrink-0 text-right font-mono text-[#6a6a6a]">
        {required != null ? `${lowerBetter ? '≤' : '≥'} ${required.toFixed(decimals)}` : '—'}
      </span>
      {disabled ? (
        <span className="w-3.5 shrink-0 text-center font-bold text-[#6a6a6a]">⊘</span>
      ) : (
        <span className="flex shrink-0 items-center gap-0.5">
          <span className={`w-3.5 text-center font-bold ${passed ? 'text-green-500' : 'text-amber-500'}`}>{passed ? '✓' : '!'}</span>
          <span className={`w-3.5 text-center text-[10px] font-medium ${passed && ratio >= 1.15 ? 'text-green-500' : 'invisible'}`}>
            {passed && ratio >= 1.15 ? (ratio >= 1.5 ? (lowerBetter ? '↓↓' : '↑↑') : (lowerBetter ? '↓' : '↑')) : '·'}
          </span>
        </span>
      )}
    </div>
  );
}

function getElementMetrics(result: CalculationResult, el: ElementResultItem) {
  const isCw = el.type === 'carriageway';
  const sidewalkNumber = !isCw
    ? result.elements!.filter(item => item.type === 'sidewalk' && item.index <= el.index).length
    : 0;
  return (isCw ? carriagewayMetrics : sidewalkMetrics).flatMap(metric => {
    const value = el[metric.key];
    if (typeof value !== 'number') return [];
    const fallbackCriterion = result.criteria.find(c => {
      const name = c.name.toLowerCase();
      if (isCw) {
        return metric.criterion === 'EIR'
          ? /eir|rei/.test(name)
          : name.startsWith(metric.criterion.toLowerCase());
      }
      const swMatch = name.match(/\bsw\s*#?(\d+)/);
      const legacyMatch = name.match(/#?e(\d+)/);
      const number = swMatch ? Number(swMatch[1]) : legacyMatch ? Number(legacyMatch[1]) + 1 : 0;
      return number === sidewalkNumber && name.includes(metric.criterion.toLowerCase());
    });
    return [{
      ...metric,
      value,
      passed: el.criteria_passed?.[metric.criterion] ?? fallbackCriterion?.passed ?? el.compliant,
      required: el.criteria_required?.[metric.criterion] ?? fallbackCriterion?.required,
      lowerBetter: metric.criterion === 'TI',
      disabledKey: `${el.index}:${metric.criterion}`,
      compliance: metric.criterion !== 'EIR',
    }];
  });
}

const QuickInfoPanel: React.FC<QuickInfoPanelProps> = ({
  result,
  loading,
  tramoId,
  projectName,
  needsCalculation,
  onDocumentSaved,
}) => {
  const lightingClass = useConfigStore(s => s.lighting_class);
  const language = useConfigStore(s => s.language);
  const baseConfig = buildCalculationRequest();
  const config = { ...baseConfig, lighting_class: lightingClass, language };
  const { t } = useI18n();
  const {
    pdfLoading,
    excelLoading,
    error: pdfError,
    handleDownload,
    disabled: downloadDisabled,
  } = useReportDownload({
    result,
    configOverride: result?.config,
    tramoId,
    needsCalculation,
    onDocumentSaved,
  });

  const [disabledCriteria, setDisabledCriteria] = useState<Set<string>>(new Set());
  const [openElements, setOpenElements] = useState<Set<number>>(new Set());
  const hasCompleteResult = Boolean(result?.luminaire && Array.isArray(result?.criteria));
  const poleLocations = useMemo(
    () => result ? luminaireLocationLabels(result.config ?? {}) : [],
    [result],
  );

  const toggleCriterion = useCallback((name: string) => {
    setDisabledCriteria(prev => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  }, []);

  useEffect(() => {
    setOpenElements(new Set(result?.elements?.map(el => el.index) ?? []));
    setDisabledCriteria(new Set());
  }, [result]);

  const toggleElement = useCallback((index: number) => {
    setOpenElements(prev => {
      const next = new Set(prev);
      next.has(index) ? next.delete(index) : next.add(index);
      return next;
    });
  }, []);

  const effectiveCompliant = useMemo(() => {
    if (!result) return false;
    if (!result.elements?.length) return result.compliant;
    return result.elements.every(el => getElementMetrics(result, el).every(metric => (
      !metric.compliance || metric.passed || disabledCriteria.has(metric.disabledKey)
    )));
  }, [result, disabledCriteria]);

  return (
    <div className="bg-[#FFFFFF] rounded-xl border border-[#E8E2D8] shadow-sm overflow-hidden">
      <div className="flex items-center justify-between gap-2 border-b border-[#E8E2D8] bg-[#FCF9F5] px-3 py-2">
        <h3 className="min-w-0 truncate font-semibold text-[#6A6A6A] text-sm flex items-center gap-2">
          <svg className="w-4 h-4 text-[#1E1E1E]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
          </svg>
          {t('results.summary')}
        </h3>
        <div className="flex flex-shrink-0 items-center gap-1.5">
          <ReportDownloadButtons
            pdfLoading={pdfLoading}
            excelLoading={excelLoading}
            disabled={downloadDisabled}
            onDownload={handleDownload}
          />
          <MeasurementsButton
            config={buildReportRequestBody(config, result?.config)}
            disabled={downloadDisabled}
            tramoId={tramoId}
          />
        </div>
      </div>
      {pdfError && (
        <div className="mx-3 mt-2 flex items-center gap-2 rounded-lg border-[#B42318]/25 bg-[#FDECEA] p-2 text-xs text-[#B42318]">
          <svg className="h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          {pdfError}
        </div>
      )}
      <div className="space-y-2 p-3">
        {loading ? (
          <div className="py-5 text-center">
            <div className="mx-auto mb-2 h-6 w-6 animate-spin rounded-full border-2 border-[#1E1E1E] border-t-transparent"/>
            <p className="text-sm text-[#A09A91]">{t('actions.calculating')}</p>
            <p className="text-xs text-[#6a6a6a] mt-1">{t('results.running')}</p>
          </div>
        ) : hasCompleteResult && result ? (
          <>

            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
              <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                effectiveCompliant ? 'bg-[#1F7A4D]/10 text-[#1F7A4D]' : 'bg-[#F5EDE0] text-[#B7791F]'
              }`}>
                <span className={`h-1.5 w-1.5 rounded-full ${effectiveCompliant ? 'bg-green-500' : 'bg-amber-500'}`} />
                {effectiveCompliant ? t('status.pass') : t('status.fail')}
              </span>
              <span className="text-[#8A847A]">·</span>
              <span className="text-[#A09A91]">EN 13201 {config.lighting_class}</span>
              <span className="text-[#8A847A]">·</span>
              <span className="truncate max-w-[160px] text-[#6A6A6A]" title={result.luminaire.luminaire_name}>
                {result.luminaire.luminaire_name}
              </span>
              <span className="text-[#8A847A]">·</span>
              <span className="text-[#A09A91]">{(result.luminaire.power ?? 0).toFixed(0)} W</span>
              <span className="text-[#8A847A]">·</span>
              <span className="text-[#A09A91]">{(result.luminaire.flux ?? 0).toFixed(0)} lm</span>
              <span className="text-[#8A847A]">·</span>
              <span className="text-[#A09A91]">CRI {result.luminaire.cri ?? 70}</span>
              <span className="text-[#8A847A]">·</span>
              <span className="text-[#A09A91]">{(result.luminaire.efficiency ?? 0).toFixed(1)} lm/W</span>
            </div>

            {poleLocations.length > 0 && (
              <div className="rounded-md border border-violet-100 bg-violet-50/50 px-2 py-1.5 text-xs text-[#6A6A6A]">
                <span className="font-semibold text-violet-700">{t('geometry.luminaireLocation')}:</span>{' '}
                {poleLocations.join(' · ')}
              </div>
            )}

            {result.elements && result.elements.length > 0 && (
              <div className="space-y-1 border-t border-[#E8E2D8] pt-2">
                <div className="text-[10px] font-bold uppercase tracking-wider text-[#6a6a6a] mb-1">
                  {t('geometry.crossSection')}
                </div>
                {result.elements.slice().sort((a, b) => a.index - b.index).map((el: ElementResultItem) => {
                  const isCw = el.type === 'carriageway';
                  const cls = isCw ? 'text-[#333333]' : 'text-[#1F7A4D]';
                  const label = roadElementLabel(el, el.index);
                  const metrics = getElementMetrics(result, el).map(metric => ({
                    ...metric,
                    disabled: disabledCriteria.has(metric.disabledKey),
                  }));
                  const elementCompliant = metrics.every(metric => (
                    !metric.compliance || metric.passed || metric.disabled
                  ));
                  const isOpen = openElements.has(el.index);
                  return (
                    <div key={el.index} className="rounded-md border border-[#E8E2D8] bg-[#FFFFFF] text-[11px]">
                      <button type="button" onClick={() => toggleElement(el.index)} aria-expanded={isOpen}
                        className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-[#FFFFFF]/70">
                        <span className={`w-10 shrink-0 font-semibold ${cls}`}>{label}</span>
                        <span className="text-[10px] text-[#A09A91]">{isCw ? el.lighting_class : el.pedestrian_class}</span>
                        <span className="min-w-0 flex-1 truncate font-mono text-[10px]">
                          {metrics.map((metric, index) => (
                            <React.Fragment key={metric.key}>
                              {index > 0 && <span className="px-1 text-[#8A847A]">·</span>}
                              <span className={metric.disabled ? 'text-[#6a6a6a] line-through' : metric.passed ? 'text-[#1F7A4D]' : 'text-[#B7791F]'}>{metric.label} {metric.value.toFixed(metric.decimals)}</span>
                            </React.Fragment>
                          ))}
                        </span>
                        <span className={`shrink-0 text-[10px] font-medium ${elementCompliant ? 'text-[#1F7A4D]' : 'text-[#B7791F]'}`}>
                          {elementCompliant ? '✓' : '!'} {elementCompliant ? t('status.pass') : t('status.fail')}
                        </span>
                        <span className="w-3 text-center text-[#A09A91]">{isOpen ? '▾' : '▸'}</span>
                      </button>
                      {isOpen && (
                        <div className="space-y-0.5 border-t border-[#E8E2D8] py-1.5">
                          {metrics.map(metric => (
                            <MetricBarRow key={metric.key} label={metric.label} value={metric.value} required={metric.required}
                              passed={metric.passed} decimals={metric.decimals} lowerBetter={metric.lowerBetter}
                              disabled={metric.disabled} onClick={() => toggleCriterion(metric.disabledKey)}
                              title={metric.disabled ? t('results.criterionDisabled') : t('results.criterionToggle')} />
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </>
        ) : (
          <div className="py-5 text-center text-[#6a6a6a]">
            <svg className="mx-auto mb-2 h-8 w-8 opacity-30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="12" cy="12" r="5"/>
              <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
            </svg>
            <p className="text-sm">{t('results.noResults')}</p>
            <p className="text-xs mt-1">{t('results.noResultsHint')}</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default QuickInfoPanel;
