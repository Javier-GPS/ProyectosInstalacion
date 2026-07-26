import React, { useCallback, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, type NavigateFunction } from 'react-router-dom';
import { useI18n } from '../../i18n';
import type { TramoSummary } from '../../lib/tramos';
import { useColumnFilters, type ColumnFilterDef } from '../../hooks/useColumnFilters';
import TramoStatusBadge from './TramoStatusBadge';
import TramoRowMenu from './TramoRowMenu';
import MeasurementsButton from '../ui/MeasurementsButton';

interface TramosTableProps {
  tramos: TramoSummary[];
  dirtyTramoIds: Set<number>;
  busyTramoIds: Set<number>;
  flashTramoId?: number | null;
  selectedIds: Set<number>;
  onSelectionChange: (ids: Set<number>) => void;
  onOpen: (tramo: TramoSummary) => void;
  onRename: (tramo: TramoSummary, next: string) => void;
  onDuplicate: (tramo: TramoSummary) => void;
  onDelete: (tramo: TramoSummary) => void;
  onDownloadPdf: (tramo: TramoSummary) => void;
  onDownloadExcel: (tramo: TramoSummary) => void;
  onLoadMeasurementsConfig: (tramo: TramoSummary) => Promise<any>;
  locked?: boolean;
}

const ROW_HEIGHT = 64;
const OVERSCAN = 5;

const formatValue = (value: number | undefined, digits = 2): string => {
  if (value === undefined || value === null || Number.isNaN(value)) return '—';
  return value.toFixed(digits);
};

const formatUpdated = (iso: string | null | undefined, t: (key: string) => string): string => {
  if (!iso) return t('tramos.updated.never');
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return t('tramos.updated.never');
  return date.toLocaleString('es', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
};

interface TramoRowProps {
  tramo: TramoSummary;
  dirty: boolean;
  busy: boolean;
  flash: boolean;
  selected: boolean;
  onToggle: (id: number) => void;
  t: (key: string) => string;
  navigate: NavigateFunction;
  onRename: (tramo: TramoSummary, next: string) => void;
  onDuplicate: (tramo: TramoSummary) => void;
  onDelete: (tramo: TramoSummary) => void;
  onDownloadPdf: (tramo: TramoSummary) => void;
  onDownloadExcel: (tramo: TramoSummary) => void;
  onLoadMeasurementsConfig: (tramo: TramoSummary) => Promise<any>;
  locked?: boolean;
}

const TramoRow: React.FC<TramoRowProps> = React.memo(({
  tramo, dirty, busy, flash, selected, onToggle, t, navigate, locked,
  onRename, onDuplicate, onDelete, onDownloadPdf, onDownloadExcel, onLoadMeasurementsConfig,
}) => {
  const status = dirty ? 'dirty' : tramo.status;
  const hasValidResult = tramo.has_result && status !== 'missing_config' && status !== 'config_error';
  const summary = tramo.compliance_summary;
  const isAlternative = Boolean(tramo.parent_section_id);
  const href = `/projects/${tramo.project_id}/tramos/${tramo.id}`;
  const updatedLabel = useMemo(
    () => formatUpdated(tramo.last_calculated_at ?? tramo.updated_at, t),
    [tramo.last_calculated_at, tramo.updated_at, t],
  );

  const handleRowClick = useCallback(() => { if (!locked) navigate(href); }, [locked, navigate, href]);
  const stopPropagation = useCallback((e: React.MouseEvent) => e.stopPropagation(), []);
  const handleLinkClick = useCallback((e: React.MouseEvent) => { e.stopPropagation(); if (locked) e.preventDefault(); }, [locked]);
  const handleRename = useCallback((next: string) => onRename(tramo, next), [onRename, tramo]);
  const handleDuplicate = useCallback(() => onDuplicate(tramo), [onDuplicate, tramo]);
  const handleDelete = useCallback(() => onDelete(tramo), [onDelete, tramo]);
  const handlePdf = useCallback(() => onDownloadPdf(tramo), [onDownloadPdf, tramo]);
  const handleExcel = useCallback(() => onDownloadExcel(tramo), [onDownloadExcel, tramo]);
  const handleCheckboxClick = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    e.stopPropagation();
    onToggle(tramo.id);
  }, [onToggle, tramo.id]);

  return (
    <tr
      id={`tramo-row-${tramo.id}`}
      onClick={handleRowClick}
      className={`${locked ? 'cursor-not-allowed opacity-70' : 'cursor-pointer'} border-b border-[#E8E2D8] last:border-b-0 transition-colors duration-500 ${
        flash ? '!bg-[#1F7A4D]/30' : selected ? 'bg-[#1E1E1E]/6' : isAlternative ? 'bg-[#FFFFFF] hover:bg-[#1E1E1E]/40' : 'bg-[#FCF9F5]/60 hover:bg-[#FFFFFF]'}`}
    >
      <td className="w-10 px-2 py-3 text-center" onClick={stopPropagation}>
        <input type="checkbox" checked={selected} onChange={handleCheckboxClick} disabled={locked}
          className="h-4 w-4 cursor-pointer rounded border-[#D4CEC6] text-[#1E1E1E] focus:ring-[#1E1E1E]/15 disabled:cursor-not-allowed" />
      </td>
      <td className="px-4 py-3">
        <div className={`flex items-center gap-2 ${isAlternative ? 'pl-6' : ''}`}>
          {isAlternative ? (
            <span className="h-5 w-5 rounded-bl-lg border-b-2 border-l-2 border-[#D4CEC6]" aria-hidden="true" />
          ) : (
            <span className="h-2.5 w-2.5 rounded-full bg-[#1E1E1E] shadow-sm" aria-hidden="true" />
          )}
          <div className="min-w-0">
            <Link to={href} onClick={handleLinkClick}
              className={`${isAlternative ? 'font-medium text-[#6A6A6A]' : 'font-bold text-[#1E1E1E]'} block truncate hover:text-[#333333]`} title={tramo.name}>
              {tramo.name}
            </Link>
            <div className={`mt-0.5 text-[11px] font-semibold uppercase tracking-wide ${isAlternative ? 'text-[#1E1E1E]' : 'text-[#6a6a6a]'}`}>
              {isAlternative ? 'Alternativa' : 'Tramo principal'}
            </div>
          </div>
        </div>
        {tramo.description && (
          <div className={`mt-0.5 truncate text-xs text-[#A09A91] ${isAlternative ? 'pl-14' : 'pl-5'}`} title={tramo.description}>
            {tramo.description}
          </div>
        )}
      </td>
      <td className="px-4 py-3"><TramoStatusBadge status={status as any} /></td>
      <td className="px-4 py-3 font-mono text-xs">
        {summary && status !== 'config_error' && status !== 'missing_config' && status !== 'calculation_pending' ? (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            {([
              ['Lavg', summary.Lavg, 2] as const,
              ['Uo', summary.Uo, 3] as const,
              ['Ul', summary.Ul, 3] as const,
              ['TI', summary.TI, 1] as const,
              ['SR', summary.SR, 3] as const,
              ['REI', summary.EIR, 3, true] as const,
            ]).map(([name, val, digits, infoOnly]) => {
              if (val === undefined) return null;
              const passed = (summary as any).criteria_passed?.[name];
              const cls = infoOnly ? 'text-[#A09A91]' : passed === true ? 'text-[#1F7A4D]' : passed === false ? 'text-[#B42318]' : 'text-[#6A6A6A]';
              return <span key={name} className={cls}>{name} {val.toFixed(digits)}{name === 'TI' ? '%' : ''}</span>;
            })}
          </div>
        ) : (
          <span className="text-[#6a6a6a]">{t('tramos.metrics.empty')}</span>
        )}
      </td>
      <td className="px-4 py-3 text-xs text-[#A09A91]">{updatedLabel}</td>
      <td className="px-4 py-3" onClick={stopPropagation}>
        <div className="flex items-center gap-1">
          {hasValidResult ? (
            <button type="button" onClick={handlePdf} disabled={busy || locked}
              className="inline-flex items-center gap-1 rounded-md border border-[#B42318]/25 bg-[#FDECEA] px-2 py-1 text-xs font-semibold text-[#B42318] hover:bg-[#B42318]/20 disabled:opacity-50"
              title={t('tramos.reports.pdf')}>
              {busy ? (
                <svg className="animate-spin" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" strokeDasharray="32" strokeDashoffset="32" strokeLinecap="round" /></svg>
              ) : (
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /></svg>
              )}
              PDF
            </button>
          ) : <span className="text-xs text-[#8A847A]">PDF</span>}
          {hasValidResult ? (
            <button type="button" onClick={handleExcel} disabled={busy || locked}
              className="inline-flex items-center gap-1 rounded-md border border-[#1F7A4D]/25 bg-[#1F7A4D]/10 px-2 py-1 text-xs font-semibold text-[#1F7A4D] hover:bg-[#1F7A4D]/20 disabled:opacity-50"
              title={t('tramos.reports.excel')}>
              {busy ? (
                <svg className="animate-spin" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" strokeDasharray="32" strokeDashoffset="32" strokeLinecap="round" /></svg>
              ) : (
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /></svg>
              )}
              Excel
            </button>
          ) : <span className="text-xs text-[#8A847A]">Excel</span>}
          {hasValidResult ? (
            <MeasurementsButton
              compact
              tramoId={tramo.id}
              disabled={locked}
              loadConfig={() => onLoadMeasurementsConfig(tramo)}
            />
          ) : <span className="text-xs text-[#8A847A]">{t('tramos.reports.measurements')}</span>}
        </div>
      </td>
      <td className="px-2 py-3 text-right" onClick={stopPropagation}>
        <TramoRowMenu tramo={tramo} busy={busy || Boolean(locked)}
          onRename={handleRename} onDuplicate={handleDuplicate} onDelete={handleDelete}
          onOpen={useCallback(() => navigate(href), [navigate, href])} />
      </td>
    </tr>
  );
});
TramoRow.displayName = 'TramoRow';

const TramosTable: React.FC<TramosTableProps> = ({
  tramos, dirtyTramoIds, busyTramoIds, flashTramoId, selectedIds,
  onSelectionChange, onRename, onDuplicate, onDelete, onDownloadPdf, onDownloadExcel, onLoadMeasurementsConfig, locked,
}) => {
  const { t } = useI18n();
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [containerHeight, setContainerHeight] = useState(600);

  const handleToggle = useCallback((id: number) => {
    if (locked) return;
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id); else next.add(id);
    onSelectionChange(next);
  }, [selectedIds, onSelectionChange, locked]);

  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const t of tramos) {
      const s = dirtyTramoIds.has(t.id) ? 'dirty' : t.status;
      counts[s] = (counts[s] || 0) + 1;
    }
    return counts;
  }, [tramos, dirtyTramoIds]);

  const filterDefs: ColumnFilterDef<TramoSummary>[] = useMemo(() => [
    { key: 'name', getValue: item => item.name },
    { key: 'status', getValue: item => dirtyTramoIds.has(item.id) ? 'dirty' : item.status, exact: true },
    { key: 'metrics', getValue: item => {
      const s = item.compliance_summary;
      return s ? [s.Lavg, s.Uo, s.Ul, s.TI, s.EIR, s.SR].filter(v => v !== undefined).join(' ') : '';
    }},
    { key: 'updated', getValue: item => formatUpdated(item.last_calculated_at ?? item.updated_at, t) },
  ], [dirtyTramoIds, t]);

  const { filters, setFilter, filteredData } = useColumnFilters(tramos, filterDefs);

  const handleFilterChange = useCallback((key: string, value: string) => {
    if (selectedIds.size > 0) onSelectionChange(new Set());
    setFilter(key, value);
  }, [onSelectionChange, selectedIds.size, setFilter]);

  const filteredIds = useMemo(() => filteredData.map(t => t.id), [filteredData]);
  const filteredIdSet = useMemo(() => new Set(filteredIds), [filteredIds]);
  const allSelected = filteredIds.length > 0 && filteredIds.every(id => selectedIds.has(id));
  const someSelected = filteredIds.some(id => selectedIds.has(id)) && !allSelected;

  const handleSelectAll = useCallback(() => {
    if (locked) return;
    const next = new Set(selectedIds);
    if (allSelected) {
      for (const id of filteredIdSet) next.delete(id);
    } else {
      for (const id of filteredIds) next.add(id);
    }
    onSelectionChange(next);
  }, [allSelected, filteredIds, filteredIdSet, onSelectionChange, locked, selectedIds]);

  const totalHeight = filteredData.length * ROW_HEIGHT;
  const visibleStart = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
  const visibleEnd = Math.min(filteredData.length, Math.ceil((scrollTop + containerHeight) / ROW_HEIGHT) + OVERSCAN);
  const visibleSlice = filteredData.slice(visibleStart, visibleEnd);
  const offsetY = visibleStart * ROW_HEIGHT;

  const handleScroll = useCallback(() => {
    if (containerRef.current) {
      setScrollTop(containerRef.current.scrollTop);
      setContainerHeight(containerRef.current.clientHeight);
    }
  }, []);

  const observeRef = useCallback((node: HTMLDivElement | null) => {
    if (node) {
      containerRef.current = node;
      setContainerHeight(node.clientHeight || 600);
    }
  }, []);

  return (
    <div className="overflow-visible rounded-xl border border-[#E8E2D8] bg-[#FFFFFF] shadow-sm">
      {selectedIds.size > 0 && (
        <div className="flex items-center gap-2 border-b border-[#E8E2D8] bg-[#1E1E1E]/6 px-4 py-2">
          <span className="text-sm font-medium text-[#1E1E1E]">
            {t('tramos.selectedCount', { count: selectedIds.size })}
          </span>
        </div>
      )}
      <div className="flex flex-col">
        <div className="sticky top-0 z-10">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#E8E2D8] bg-[#FCF9F5] text-left text-xs font-semibold uppercase tracking-wider text-[#A09A91]">
                <th className="w-10 px-2 py-3 text-center">
                  <input type="checkbox" checked={allSelected}
                    ref={(el) => { if (el) el.indeterminate = someSelected; }}
                    onChange={handleSelectAll}
                    disabled={locked}
                    className="h-4 w-4 cursor-pointer rounded border-[#D4CEC6] text-[#1E1E1E] focus:ring-[#1E1E1E]/15 disabled:cursor-not-allowed" />
                </th>
                <th className="px-4 py-3">{t('tramos.columns.name')}</th>
                <th className="px-4 py-3">{t('tramos.columns.status')}</th>
                <th className="px-4 py-3">{t('tramos.columns.metrics')}</th>
                <th className="px-4 py-3">{t('tramos.columns.updated')}</th>
                <th className="px-4 py-3">{t('tramos.columns.reports')}</th>
                <th className="px-2 py-3 text-right">{t('tramos.columns.actions')}</th>
              </tr>
              <tr className="border-b border-[#E8E2D8] bg-[#FCF9F5]/50">
                <th className="w-10 px-1 py-1" />
                <th className="px-1 py-1">
                  <input value={filters.name || ''} onChange={e => handleFilterChange('name', e.target.value)} placeholder={t('tramos.columns.name')}
                    className="w-full px-1.5 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-[#1E1E1E]" />
                </th>
                <th className="px-1 py-1">
                  <select value={filters.status || ''} onChange={e => handleFilterChange('status', e.target.value)}
                    className="w-full px-1 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-[#1E1E1E]">
                    <option value="">{t('tramos.filterAll', { total: tramos.length })}</option>
                    <option value="pending">{t('tramos.status.pending')} ({statusCounts.pending ?? 0})</option>
                    <option value="calculation_pending">{t('tramos.status.calculationPending')} ({statusCounts.calculation_pending ?? 0})</option>
                    <option value="no_pcb_capacity">{t('tramos.status.noPcbCapacity')} ({statusCounts.no_pcb_capacity ?? 0})</option>
                    <option value="compliant">{t('tramos.status.compliant')} ({statusCounts.compliant ?? 0})</option>
                    <option value="non_compliant">{t('tramos.status.nonCompliant')} ({statusCounts.non_compliant ?? 0})</option>
                    <option value="config_error">{t('tramos.status.config_error')} ({statusCounts.config_error ?? 0})</option>
                    <option value="missing_config">{t('tramos.status.missing_config')} ({statusCounts.missing_config ?? 0})</option>
                    <option value="dirty">{t('tramos.status.dirty')} ({statusCounts.dirty ?? 0})</option>
                  </select>
                </th>
                <th className="px-1 py-1">
                  <input value={filters.metrics || ''} onChange={e => handleFilterChange('metrics', e.target.value)} placeholder="Lavg Uo Ul..."
                    className="w-full px-1.5 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-[#1E1E1E]" />
                </th>
                <th className="px-1 py-1">
                  <input value={filters.updated || ''} onChange={e => handleFilterChange('updated', e.target.value)} placeholder="Fecha"
                    className="w-full px-1.5 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-[#1E1E1E]" />
                </th>
                <th className="px-1 py-1" />
                <th className="px-1 py-1" />
              </tr>
            </thead>
          </table>
        </div>
        <div ref={observeRef} onScroll={handleScroll}
          className="overflow-y-auto" style={{ maxHeight: 'calc(100vh - 380px)', minHeight: 200 }}>
          <div style={{ height: totalHeight, position: 'relative' }}>
            <table className="w-full text-sm" style={{ transform: `translateY(${offsetY}px)` }}>
              <tbody>
                {visibleSlice.map(tramo => {
                  const id = tramo.id;
                  return (
                    <TramoRow key={id} tramo={tramo}
                      dirty={dirtyTramoIds.has(id)}
                      busy={busyTramoIds.has(id)}
                      flash={flashTramoId === id}
                      selected={selectedIds.has(id)}
                      onToggle={handleToggle}
                      t={t} navigate={navigate}
                      locked={locked}
                      onRename={onRename} onDuplicate={onDuplicate} onDelete={onDelete}
                      onDownloadPdf={onDownloadPdf} onDownloadExcel={onDownloadExcel}
                      onLoadMeasurementsConfig={onLoadMeasurementsConfig} />
                  );
                })}
                {visibleSlice.length === 0 && tramos.length > 0 && (
                  <tr><td colSpan={7} className="px-4 py-8 text-center text-sm text-[#6a6a6a]">
                    {t('tramos.noFilterResults')}
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TramosTable;
