import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useI18n } from '../../i18n';
import {
  DIM_PARAM_KEYS,
  TRAMO_PARAM_DEFS,
  TRAMO_PARAM_GROUPS,
  autoSuggestMapping,
  buildConfigsFromSheet,
  downloadTemplate,
  parseExcelFile,
  type BuiltRow,
  type ColumnMapping,
  type DimMatchResult,
  type ManualValues,
  type ParsedSheet,
  type TramoParamDef,
  type ValueSource,
} from '../../lib/tramosExcelImport';
import type { AuthFetch } from '../../auth/AuthContext';
import { bulkImportTramos } from '../../lib/tramos';
import { useConfigStore } from '../../store/useConfigStore';

interface ImportTramosExcelModalProps {
  open: boolean;
  onClose: () => void;
  onImported: () => void;
  projectId: number;
  authFetch: AuthFetch;
}

type Phase = 'upload' | 'mapping' | 'submitting' | 'result';

interface DragState {
  source: 'pool' | 'slot';
  paramKey?: string;
}

const previewLimit = 10;

const ImportTramosExcelModal: React.FC<ImportTramosExcelModalProps> = ({
  open,
  onClose,
  onImported,
  projectId,
  authFetch,
}) => {
  const { t } = useI18n();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [phase, setPhase] = useState<Phase>('upload');
  const [fileName, setFileName] = useState<string | null>(null);
  const [sheet, setSheet] = useState<ParsedSheet | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [mapping, setMapping] = useState<ColumnMapping>({});
  const [manualValues, setManualValues] = useState<ManualValues>({});
  const [drag, setDrag] = useState<DragState | null>(null);
  const [overKey, setOverKey] = useState<string | null>(null);
  const [poolFilter, setPoolFilter] = useState('');
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitResult, setSubmitResult] = useState<{
    created: number;
    failed: number;
    errors: Array<{ row: number; name: string; error: string }>;
  } | null>(null);
  const [catalogOptions, setCatalogOptions] = useState<Record<string, string[]>>({});

  const defaults = useConfigStore.getState();

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    Promise.all([
      fetch('/api/ldt/dimensions').then(r => r.json()),
      fetch('/api/ldt/catalog').then(r => r.json()),
    ])
      .then(([dimsData, catalogData]: [any, any[]]) => {
        if (cancelled) return;
        const opts: Record<string, string[]> = {};
        if (Array.isArray(dimsData.gamas)) opts.gama = dimsData.gamas.map((d: any) => d.name);
        if (Array.isArray(dimsData.difusores)) opts.difusor = dimsData.difusores.map((d: any) => d.name);
        if (Array.isArray(dimsData.lentes)) opts.lente = dimsData.lentes.map((d: any) => d.name);
        if (Array.isArray(dimsData.led_types)) opts.led_type = dimsData.led_types.map((d: any) => d.name);
        if (Array.isArray(catalogData)) {
          const manufacturers = [...new Set(catalogData.map((ldt: any) => ldt.manufacturer).filter(Boolean))].sort();
          if (manufacturers.length > 0) opts.manufacturer = manufacturers;
        }
        setCatalogOptions(opts);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;
    const body = document.body;
    const previousOverflow = body.style.overflow;
    const previousPaddingRight = body.style.paddingRight;
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
    body.style.overflow = 'hidden';
    if (scrollbarWidth > 0) {
      body.style.paddingRight = `${scrollbarWidth}px`;
    }
    return () => {
      body.style.overflow = previousOverflow;
      body.style.paddingRight = previousPaddingRight;
    };
  }, [open]);

  useEffect(() => {
    if (!open) {
      setPhase('upload');
      setFileName(null);
      setSheet(null);
      setParseError(null);
      setMapping({});
      setManualValues({});
      setDrag(null);
      setOverKey(null);
      setPoolFilter('');
      setSubmitError(null);
      setSubmitResult(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  }, [open]);

  const handleFile = useCallback(async (file: File) => {
    setParseError(null);
    setSubmitError(null);
    setSubmitResult(null);
    const isExcel = /\.(xlsx|xls|csv)$/i.test(file.name);
    if (!isExcel) {
      setParseError(t('tramos.import.invalidFile'));
      return;
    }
    setFileName(file.name);
    try {
      const parsed = await parseExcelFile(file);
      if (parsed.headers.length === 0) {
        setParseError(t('tramos.import.emptyFile'));
        return;
      }
      setSheet(parsed);
      setMapping({});
      setManualValues({});
      setPoolFilter('');
      setPhase('mapping');
    } catch (err: any) {
      setParseError(err?.message || t('tramos.import.parseError'));
      setSheet(null);
    }
  }, [t]);

  const handleDropFile = useCallback((event: React.DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    const file = event.dataTransfer.files?.[0];
    if (file) {
      void handleFile(file);
    }
  }, [handleFile]);

  const [dimOverrides, setDimOverrides] = useState<Record<number, Record<string, string>>>({});

  const handleDimOverride = useCallback((rowIndex: number, paramKey: string, value: string) => {
    setDimOverrides(prev => {
      const next = { ...prev };
      const rowOverrides = { ...(next[rowIndex] ?? {}) };
      rowOverrides[paramKey] = value;
      if (next[rowIndex]) next[rowIndex] = rowOverrides;
      else next[rowIndex] = rowOverrides;
      return next;
    });
  }, []);

  const previewRows: BuiltRow[] = useMemo(() => {
    if (!sheet) return [];
    return buildConfigsFromSheet({
      sheet,
      mapping,
      manualValues,
      defaults: defaultsSnapshot(defaults),
      rowLimit: previewLimit,
      catalogOptions,
    });
  }, [sheet, mapping, manualValues, defaults, catalogOptions]);

  const totalConfiguredRows = useMemo(() => sheet?.rows.length ?? 0, [sheet]);

  const mappingStats = useMemo(() => {
    const total = TRAMO_PARAM_DEFS.length;
    const mappedColumns = Object.values(mapping).filter(v => v != null).length;
    const manualCount = Object.values(manualValues).filter(v => (v ?? '').trim() !== '').length;
    return { total, mappedColumns, manualCount };
  }, [mapping, manualValues]);

  const handleStartDragFromPool = (event: React.DragEvent<HTMLButtonElement>, columnIndex: number) => {
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', String(columnIndex));
    setDrag({ source: 'pool', paramKey: undefined });
  };

  const handleStartDragFromSlot = (event: React.DragEvent<HTMLButtonElement>, paramKey: string) => {
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', mapping[paramKey] ?? '');
    setDrag({ source: 'slot', paramKey });
  };

  const handleDropOnSlot = (event: React.DragEvent<HTMLDivElement>, paramKey: string) => {
    event.preventDefault();
    setOverKey(null);
    setDrag(null);
    if (!sheet) return;
    const raw = event.dataTransfer.getData('text/plain');
    if (raw === '' || Number.isNaN(Number(raw))) return;
    const columnIndex = raw;
    setMapping(prev => {
      const next: ColumnMapping = { ...prev };
      if (drag?.source === 'slot' && drag.paramKey && drag.paramKey !== paramKey) {
        next[drag.paramKey] = null;
        next[paramKey] = columnIndex;
      } else if (drag?.source === 'slot' && drag.paramKey === paramKey) {
        return prev;
      } else {
        next[paramKey] = columnIndex;
      }
      return cleanMapping(next);
    });
  };

  const handleClearSlot = (paramKey: string) => {
    setMapping(prev => cleanMapping({ ...prev, [paramKey]: null }));
  };

  const handleDropOnPool = (event: React.DragEvent) => {
    event.preventDefault();
    setOverKey(null);
    if (drag?.source === 'slot' && drag.paramKey) {
      handleClearSlot(drag.paramKey);
    }
    setDrag(null);
  };

  const handleClearAll = () => {
    setMapping({});
    setManualValues({});
  };

  const handleAutoMap = () => {
    if (!sheet) return;
    setMapping(autoSuggestMapping(sheet.headers));
  };

  const handleManualChange = (paramKey: string, value: string) => {
    setManualValues(prev => {
      const next = { ...prev };
      if (value === '') {
        delete next[paramKey];
      } else {
        next[paramKey] = value;
      }
      return next;
    });
  };

  const handleSubmit = async () => {
    if (!sheet) return;
    setPhase('submitting');
    setSubmitError(null);
    setSubmitResult(null);
    try {
      const built = buildConfigsFromSheet({
        sheet,
        mapping,
        manualValues,
        defaults: defaultsSnapshot(defaults),
        catalogOptions,
      });
      for (const row of built) {
        const overrides = dimOverrides[row.rowIndex];
        if (overrides) {
          for (const [key, val] of Object.entries(overrides)) {
            row.config[key] = val;
          }
        }
      }
      const fallbackNames = new Set<string>();
      const items = built.map((row, index) => {
        const config = stripVisualFields(row.config);
        const rawName = row.name?.trim() || '';
        let name = rawName;
        if (!name) {
          let n = index + 1;
          let candidate = `Tramo ${n}`;
          while (fallbackNames.has(candidate.toLowerCase())) {
            n += 1;
            candidate = `Tramo ${n}`;
          }
          fallbackNames.add(candidate.toLowerCase());
          name = candidate;
        } else {
          let uniqueName = name;
          let suffix = 2;
          while (fallbackNames.has(uniqueName.toLowerCase())) {
            uniqueName = `${name} (${suffix})`;
            suffix += 1;
          }
          name = uniqueName;
          fallbackNames.add(name.toLowerCase());
        }
        return {
          name,
          description: row.description,
          config,
        };
      });
      const response = await bulkImportTramos(authFetch, projectId, items);
      setSubmitResult({
        created: response.created,
        failed: response.failed,
        errors: response.items
          .filter(i => i.status === 'error')
          .map(i => ({ row: i.row, name: i.name, error: i.error || '' })),
      });
      setPhase('result');
      if (response.created > 0) {
        onImported();
      }
    } catch (err: any) {
      setSubmitError(err?.message || t('tramos.import.submitError'));
      setPhase('mapping');
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4 py-4"
    >
      <div className="flex h-[94vh] w-full max-w-7xl flex-col overflow-hidden rounded-2xl bg-[#FFFFFF] shadow-2xl">
        <header className="flex items-start justify-between border-b border-[#E8E2D8] px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold text-[#1E1E1E]">{t('tramos.import.title')}</h2>
            <p className="mt-1 text-sm text-[#A09A91]">{t('tramos.import.subtitle')}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-[#6a6a6a] hover:bg-[#FFFFFF] hover:text-[#6A6A6A]"
            aria-label={t('actions.cancel')}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </header>

        <div className="relative flex flex-1 min-h-0 flex-col overflow-hidden overscroll-contain">
          {phase === 'upload' && (
            <UploadPhase
              fileInputRef={fileInputRef}
              onFile={handleFile}
              onDropFile={handleDropFile}
              fileName={fileName}
              error={parseError}
            />
          )}
          {(phase === 'mapping' || phase === 'submitting') && sheet && (
            <MappingPhase
              sheet={sheet}
              mapping={mapping}
              manualValues={manualValues}
              mappingStats={mappingStats}
              poolFilter={poolFilter}
              setPoolFilter={setPoolFilter}
              previewRows={previewRows}
              totalRows={totalConfiguredRows}
              drag={drag}
              overKey={overKey}
              defaults={defaultsSnapshot(defaults)}
              onDragStartFromPool={handleStartDragFromPool}
              onDragStartFromSlot={handleStartDragFromSlot}
              onDropOnSlot={handleDropOnSlot}
              onClearSlot={handleClearSlot}
              onClearAll={handleClearAll}
              onAutoMap={handleAutoMap}
              onManualChange={handleManualChange}
              onDropOnPool={handleDropOnPool}
              catalogOptions={catalogOptions}
              onDragEnterSlot={key => setOverKey(key)}
              onDragLeaveSlot={() => setOverKey(null)}
              submitError={submitError}
              dimOverrides={dimOverrides}
              onDimOverride={handleDimOverride}
            />
          )}
          {phase === 'result' && submitResult && (
            <ResultPhase result={submitResult} />
          )}

          {phase === 'submitting' && (
            <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 rounded-2xl bg-[#FFFFFF]/80">
              <svg className="h-8 w-8 animate-spin text-[#1E1E1E]" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <span className="text-sm font-medium text-[#6A6A6A]">{t('tramos.import.submitting')}</span>
            </div>
          )}
        </div>

        <footer className="flex items-center justify-between gap-2 border-t border-[#E8E2D8] bg-[#FCF9F5] px-6 py-3">
          {phase === 'mapping' && (
            <>
              <div className="text-xs text-[#A09A91]">
                {t('tramos.import.mappingSummary', {
                  columns: mappingStats.mappedColumns,
                  manual: mappingStats.manualCount,
                  total: totalConfiguredRows,
                })}
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={onClose}
                  className="rounded-lg border border-[#E8E2D8] px-3 py-2 text-sm font-semibold text-[#6A6A6A] hover:bg-[#FFFFFF] disabled:opacity-50"
                >
                  {t('actions.cancel')}
                </button>
                <button
                  type="button"
                  onClick={() => void handleSubmit()}
                  className="rounded-lg bg-[#1E1E1E] px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[#333333]"
                >
                  {t('tramos.import.submit', { count: totalConfiguredRows })}
                </button>
              </div>
            </>
          )}
          {phase === 'submitting' && (
            <div className="flex w-full items-center justify-center gap-3">
              <svg className="h-5 w-5 animate-spin text-[#1E1E1E]" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <span className="text-sm text-[#A09A91]">{t('tramos.import.submitting')}</span>
            </div>
          )}
          {phase === 'result' && (
            <div className="ml-auto">
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg bg-[#1E1E1E] px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[#333333]"
              >
                {t('actions.continue')}
              </button>
            </div>
          )}
        </footer>
      </div>
    </div>
  );
};


const defaultsSnapshot = (state: any) => ({
  road_width: state.road_width,
  sidewalk_left: state.sidewalk_left,
  sidewalk_right: state.sidewalk_right,
  lanes: state.lanes,
  median_width: state.median_width,
  arrangement: state.arrangement,
  height: state.height,
  spacing: state.spacing,
  arm_length: state.arm_length,
  armLength: state.arm_length,
  pole_offset: state.pole_offset,
  pole_side: state.pole_side,
  tilt: state.tilt,
  armTiltAngle: state.tilt,
  optic_family: state.optic_family,
  power: state.power,
  manufacturer: state.manufacturer,
  gama: state.gama,
  difusor: state.difusor,
  lente: state.lente,
  led_type: state.led_type,
  lighting_class: state.lighting_class,
  mf: state.mf,
  pavement: state.pavement,
  cct: state.cct,
  cri: state.cri,
  language: state.language,
});

const cleanMapping = (mapping: ColumnMapping): ColumnMapping => {
  const next: ColumnMapping = {};
  Object.entries(mapping).forEach(([key, value]) => {
    if (value != null) next[key] = value;
  });
  return next;
};

const stripVisualFields = (config: Record<string, any>) => {
  const next = { ...config };
  delete next.name;
  delete next.description;
  return next;
};

interface UploadPhaseProps {
  fileInputRef: React.RefObject<HTMLInputElement>;
  onFile: (file: File) => void;
  onDropFile: (event: React.DragEvent<HTMLLabelElement>) => void;
  fileName: string | null;
  error: string | null;
}

const UploadPhase: React.FC<UploadPhaseProps> = ({ fileInputRef, onFile, onDropFile, fileName, error }) => {
  const { t } = useI18n();
  return (
    <div className="px-6 py-8">
      <label
        htmlFor="import-tramos-excel-input"
        onDragOver={event => event.preventDefault()}
        onDrop={onDropFile}
        className="flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-blue-300 bg-[#1E1E1E]/40 px-6 py-16 text-center transition-colors hover:bg-[#1E1E1E]/6"
      >
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className="text-blue-500">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="17 8 12 3 7 8" />
          <line x1="12" y1="3" x2="12" y2="15" />
        </svg>
        <div>
          <div className="text-base font-semibold text-[#6A6A6A]">{t('tramos.import.dropzoneTitle')}</div>
          <div className="mt-1 text-sm text-[#A09A91]">{t('tramos.import.dropzoneHint')}</div>
        </div>
        <span className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-[#FFFFFF] px-4 py-2 text-sm font-semibold text-[#333333] shadow-sm">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          {t('tramos.import.chooseFile')}
        </span>
        {fileName && (
          <div className="mt-2 text-xs text-[#A09A91]">{fileName}</div>
        )}
      </label>
      <input
        id="import-tramos-excel-input"
        ref={fileInputRef}
        type="file"
        accept=".xlsx,.xls,.csv"
        className="sr-only"
        onChange={event => {
          const file = event.target.files?.[0];
          if (file) onFile(file);
        }}
      />
      <div className="mt-4 text-center">
        <span className="text-xs text-[#6a6a6a]">{t('tramos.import.templateHint')}</span>
        <button
          type="button"
          onClick={downloadTemplate}
          className="ml-2 inline-flex items-center gap-1 text-xs font-semibold text-[#1E1E1E] hover:text-blue-800"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="7 10 12 15 17 10" />
            <line x1="12" y1="15" x2="12" y2="3" />
          </svg>
          {t('tramos.import.downloadTemplate')}
        </button>
      </div>
      {error && (
        <div className="mt-4 rounded-lg border border-[#B42318]/25 bg-[#FDECEA] px-4 py-3 text-sm text-[#B42318]">
          {error}
        </div>
      )}
    </div>
  );
};

interface MappingPhaseProps {
  sheet: ParsedSheet;
  mapping: ColumnMapping;
  manualValues: ManualValues;
  mappingStats: { total: number; mappedColumns: number; manualCount: number };
  poolFilter: string;
  setPoolFilter: (value: string) => void;
  previewRows: BuiltRow[];
  totalRows: number;
  drag: DragState | null;
  overKey: string | null;
  defaults: Record<string, any>;
  onDragStartFromPool: (event: React.DragEvent<HTMLButtonElement>, columnIndex: number) => void;
  onDragStartFromSlot: (event: React.DragEvent<HTMLButtonElement>, paramKey: string) => void;
  onDropOnSlot: (event: React.DragEvent<HTMLDivElement>, paramKey: string) => void;
  onClearSlot: (paramKey: string) => void;
  onClearAll: () => void;
  onAutoMap: () => void;
  onManualChange: (paramKey: string, value: string) => void;
  onDropOnPool: (event: React.DragEvent) => void;
  catalogOptions: Record<string, string[]>;
  onDragEnterSlot: (key: string) => void;
  onDragLeaveSlot: () => void;
  submitError: string | null;
  dimOverrides: Record<number, Record<string, string>>;
  onDimOverride: (rowIndex: number, paramKey: string, value: string) => void;
}

const MappingPhase: React.FC<MappingPhaseProps> = ({
  sheet, mapping, manualValues, poolFilter, setPoolFilter,
  previewRows, totalRows, drag, overKey, defaults,
  onDragStartFromPool, onDragStartFromSlot, onDropOnSlot,
  onClearSlot, onClearAll, onAutoMap, onManualChange,
  onDropOnPool, catalogOptions, onDragEnterSlot, onDragLeaveSlot, submitError,
  dimOverrides, onDimOverride,
}) => {
  const { t } = useI18n();
  const usedColumns = new Set(
    Object.values(mapping).filter((v): v is string => v != null),
  );
  const filterLc = poolFilter.toLowerCase();
  const availableColumns = sheet.headers
    .map((header, idx) => ({ header, idx }))
    .filter(({ idx }) => !usedColumns.has(String(idx)))
    .filter(({ header }) => !filterLc || header.toLowerCase().includes(filterLc));

  return (
    <div className="flex min-h-0 flex-1 flex-col xl:flex-row overscroll-contain">
      <aside
        className={`flex shrink-0 flex-col border-b border-[#E8E2D8] bg-[#FCF9F5]/40 xl:w-[340px] xl:border-b-0 xl:border-r transition-colors ${
          drag?.source === 'slot' ? 'ring-2 ring-inset ring-blue-200 bg-[#1E1E1E]/60' : ''
        }`}
        onDragOver={event => event.preventDefault()}
        onDrop={onDropOnPool}
      >
        <div className="flex items-center justify-between border-b border-[#E8E2D8] px-4 py-3">
          <h3 className="text-sm font-semibold text-[#6A6A6A]">
            {t('tramos.import.poolTitle')}
            <span className="ml-2 rounded bg-[#F0EDE8] px-1.5 py-0.5 text-[10px] font-mono text-[#A09A91]">
              {availableColumns.length}/{sheet.headers.length}
            </span>
          </h3>
          <div className="flex gap-1">
            <button type="button" onClick={onAutoMap} title={t('tramos.import.autoMapHint')}
              className="rounded-md border border-[#E8E2D8] px-2 py-1 text-[11px] font-semibold text-[#6A6A6A] hover:bg-[#F7F4EF]">
              {t('tramos.import.autoMap')}
            </button>
            <button type="button" onClick={onClearAll} title={t('tramos.import.clearAllHint')}
              className="rounded-md border border-[#E8E2D8] px-2 py-1 text-[11px] font-semibold text-[#6A6A6A] hover:bg-[#F7F4EF]">
              {t('tramos.import.clearAll')}
            </button>
          </div>
        </div>
        <div className="border-b border-[#E8E2D8] px-4 py-2">
          <input
            value={poolFilter}
            onChange={e => setPoolFilter(e.target.value)}
            placeholder={t('tramos.import.poolSearch')}
            className="w-full rounded-md border border-[#E8E2D8] bg-[#FFFFFF] px-2 py-1.5 text-xs text-[#6A6A6A] outline-none focus:border-blue-300 focus:ring-1 focus:ring-[#1E1E1E]/10"
          />
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-3">
          <p className="mb-2 text-[11px] text-[#A09A91]">{t('tramos.import.poolHint')}</p>
          <div className="space-y-1.5">
            {availableColumns.length === 0 ? (
              <div className="rounded-lg border border-dashed border-[#D4CEC6] bg-[#FFFFFF] px-3 py-6 text-center text-xs text-[#A09A91]">
                {usedColumns.size === sheet.headers.length
                  ? t('tramos.import.poolEmptyAll')
                  : t('tramos.import.poolEmpty')}
              </div>
            ) : (
              availableColumns.map(({ header, idx }) => (
                <button
                  key={idx}
                  type="button"
                  draggable
                  onDragStart={event => onDragStartFromPool(event, idx)}
                  onDragEnd={onDragLeaveSlot}
                  className={`flex w-full items-center justify-between rounded-lg border border-[#E8E2D8] bg-[#FFFFFF] px-3 py-2 text-left text-sm shadow-sm transition ${
                    drag?.source === 'pool' ? 'opacity-50' : 'hover:border-blue-300 hover:bg-[#1E1E1E]/6 cursor-grab active:cursor-grabbing'
                  }`}
                  title={t('tramos.import.dragHint')}
                >
                  <span className="truncate font-medium text-[#6A6A6A]">{header || `Columna ${idx + 1}`}</span>
                  <span className="ml-2 shrink-0 rounded bg-[#F0EDE8] px-2 py-0.5 text-[10px] font-mono text-[#A09A91]">
                    #{idx + 1}
                  </span>
                </button>
              ))
            )}
          </div>
        </div>
        <div className="border-t border-[#E8E2D8] bg-[#1E1E1E]/30 px-4 py-3 text-[11px] text-[#6A6A6A]">
          <div className="mb-1 font-semibold text-[#6A6A6A]">{t('tramos.import.legendTitle')}</div>
          <ul className="space-y-1">
            <li className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-[#1F7A4D]/100" />
              {t('tramos.import.legendColumn')}
            </li>
            <li className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-[#1E1E1E]/60" />
              {t('tramos.import.legendManual')}
            </li>
            <li className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-slate-300" />
              {t('tramos.import.legendDefault')}
            </li>
          </ul>
        </div>
      </aside>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-6 py-4">
          <div className="space-y-4">
            {TRAMO_PARAM_GROUPS.map(group => {
              const params = TRAMO_PARAM_DEFS.filter(d => d.group === group.key);
              const mappedInGroup = params.filter(p => mapping[p.key] != null || (manualValues[p.key] ?? '').trim() !== '').length;
              return (
                <section key={group.key} className="rounded-xl border border-[#E8E2D8] bg-[#FFFFFF] p-3">
                  <header className="mb-2 flex items-center justify-between">
                    <div className="text-xs font-semibold uppercase tracking-wide text-[#A09A91]">
                      {t(`tramos.import.groups.${group.key}`) || group.label}
                    </div>
                    <div className="text-[10px] font-mono text-[#6a6a6a]">
                      {mappedInGroup}/{params.length}
                    </div>
                  </header>
                  <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                    {params.map(param => (
                      <ParamSlot
                        key={param.key}
                        param={param}
                        mapping={mapping}
                        manualValues={manualValues}
                        headers={sheet.headers}
                        isOver={overKey === param.key}
                        onDragEnter={() => onDragEnterSlot(param.key)}
                        onDragLeave={onDragLeaveSlot}
                        onDrop={event => onDropOnSlot(event, param.key)}
                        onDragStart={event => onDragStartFromSlot(event, param.key)}
                        onClear={() => onClearSlot(param.key)}
                        onManualChange={value => onManualChange(param.key, value)}
                        isDragging={drag?.source === 'slot' && drag.paramKey === param.key}
                        defaultValue={defaults[param.key]}
                        catalogOptions={catalogOptions}
                      />
                    ))}
                  </div>
                </section>
              );
            })}
          </div>
        </div>
        <div className="max-h-[35%] min-h-[140px] overflow-y-auto overscroll-contain border-t border-[#E8E2D8] bg-[#FCF9F5]/40 px-6 py-3">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-[#6A6A6A]">
              {t('tramos.import.previewTitle', { shown: previewRows.length, total: totalRows })}
            </h3>
            <div className="flex items-center gap-3 text-[11px] text-[#A09A91]">
              <span className="flex items-center gap-1">
                <span className="h-2 w-2 rounded-full bg-[#1F7A4D]/100" />
                {t('tramos.import.sourceColumn')}
              </span>
              <span className="flex items-center gap-1">
                <span className="h-2 w-2 rounded-full bg-[#1E1E1E]/60" />
                {t('tramos.import.sourceManual')}
              </span>
              <span className="flex items-center gap-1">
                <span className="h-2 w-2 rounded-full bg-slate-300" />
                {t('tramos.import.sourceDefault')}
              </span>
            </div>
          </div>
          <div className="overflow-x-auto overscroll-contain rounded-xl border border-[#E8E2D8] bg-[#FFFFFF]">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-[#FCF9F5] text-left text-[11px] font-semibold uppercase tracking-wide text-[#A09A91]">
                  <th className="px-3 py-2">#</th>
                  {sheet.headers.map((header, idx) => (
                    <th key={idx} className="px-3 py-2">
                      {header || `Columna ${idx + 1}`}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {previewRows.length === 0 ? (
                  <tr>
                    <td colSpan={sheet.headers.length + 1} className="px-3 py-6 text-center text-[#6a6a6a]">
                      {t('tramos.import.noData')}
                    </td>
                  </tr>
                ) : (
                    previewRows.map((row, idx) => (
                    <tr key={idx} className="border-t border-[#E8E2D8]">
                      <td className="px-3 py-1.5 font-mono text-[#6a6a6a]">{row.rowIndex}</td>
                      {sheet.headers.map((_, colIdx) => {
                        const cell = (sheet.rows[idx] ?? [])[colIdx] ?? '';
                        const mappedParam = Object.entries(mapping).find(([, v]) => v === String(colIdx))?.[0];
                        const erroredMessages = mappedParam ? row.errorsByParam[mappedParam] : undefined;
                        const errored = Boolean(erroredMessages && erroredMessages.length > 0);
                        const isCellUsed = Boolean(mappedParam) && cell !== '';
                        const isDim = mappedParam && DIM_PARAM_KEYS.includes(mappedParam);
                        const dimResult: DimMatchResult | undefined = isDim ? row.dimMatch[mappedParam] : undefined;
                        const dimOverride = dimOverrides[row.rowIndex]?.[mappedParam ?? ''] ?? null;
                        return (
                          <td
                            key={colIdx}
                            className={`relative px-3 py-1.5 text-[#6A6A6A] ${errored ? 'bg-[#FDECEA] text-[#B42318]' : ''}`}
                            title={errored ? erroredMessages!.join('\n') : undefined}
                          >
                            <div className="flex items-center gap-1.5">
                              {isCellUsed && !isDim && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[#1F7A4D]/100" />}
                              {isCellUsed && dimResult && dimResult.status === 'exact' && (
                                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[#1F7A4D]/100" title={t('tramos.import.matchExact')} />
                              )}
                              {isCellUsed && dimResult && dimResult.status === 'auto' && (
                                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" title={`${t('tramos.import.matchAuto')} → ${dimResult.resolved}`} />
                              )}
                              {isCellUsed && dimResult && dimResult.status === 'not_found' && (
                                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[#FDECEA]0" title={t('tramos.import.matchNotFound')} />
                              )}
                              {isCellUsed && dimResult && dimResult.status === 'ambiguous' && (
                                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-purple-500" title={t('tramos.import.matchAmbiguous')} />
                              )}
                              {isDim && dimResult?.status === 'ambiguous' ? (
                                <select
                                  value={dimOverride || ''}
                                  onChange={e => {
                                    if (mappedParam) onDimOverride(row.rowIndex, mappedParam, e.target.value);
                                  }}
                                  className="max-w-[140px] truncate rounded border border-purple-300 bg-purple-50 px-1 py-0.5 text-xs text-purple-800"
                                >
                                  <option value="">{cell || '—'}</option>
                                  {dimResult.candidates.map(c => (
                                    <option key={c} value={c}>{c}</option>
                                  ))}
                                </select>
                              ) : isDim && dimResult?.status === 'not_found' ? (
                                <span className="truncate text-[#B42318]">{cell || '—'} <span className="text-[10px] text-red-400">({t('tramos.import.notFound')})</span></span>
                              ) : (
                                <span className="truncate">{cell || <span className="text-[#8A847A]">—</span>}</span>
                              )}
                            </div>
                          </td>
                        );
                      })}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          {submitError && (
            <div className="mt-3 rounded-lg border border-[#B42318]/25 bg-[#FDECEA] px-3 py-2 text-xs text-[#B42318]">
              {submitError}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const computeSource = (paramKey: string, mapping: ColumnMapping, manualValues: ManualValues): ValueSource | null => {
  const hasColumn = mapping[paramKey] != null;
  const hasManual = (manualValues[paramKey] ?? '').trim() !== '';
  if (hasColumn && hasManual) return 'column'; // primary; manual is fallback for empty cells
  if (hasColumn) return 'column';
  if (hasManual) return 'manual';
  return null;
};

interface ParamSlotProps {
  param: TramoParamDef;
  mapping: ColumnMapping;
  manualValues: ManualValues;
  headers: string[];
  isOver: boolean;
  isDragging: boolean;
  defaultValue: unknown;
  onDragEnter: () => void;
  onDragLeave: () => void;
  onDrop: (event: React.DragEvent<HTMLDivElement>) => void;
  onDragStart: (event: React.DragEvent<HTMLButtonElement>) => void;
  onClear: () => void;
  onManualChange: (value: string) => void;
  catalogOptions: Record<string, string[]>;
}

const ParamSlot: React.FC<ParamSlotProps> = ({
  param,
  mapping,
  manualValues,
  headers,
  isOver,
  isDragging,
  defaultValue,
  onDragEnter,
  onDragLeave,
  onDrop,
  onDragStart,
  onClear,
  onManualChange,
  catalogOptions,
}) => {
  const { t } = useI18n();
  const columnIndex = mapping[param.key];
  const header = columnIndex != null ? headers[Number(columnIndex)] : null;
  const manualRaw = manualValues[param.key] ?? '';
  const source = computeSource(param.key, mapping, manualValues);
  const isRequired = Boolean(param.required);
  const catalogValues = catalogOptions[param.key];
  const hasOwnEnum = param.enumValues != null && param.enumValues.length > 0;
  const hasCatalog = catalogValues != null && catalogValues.length > 0;
  const isEnum = hasOwnEnum || hasCatalog;
  const enumOptions: string[] = param.enumValues ?? catalogValues ?? [];
  const manualPlaceholder = isEnum
    ? enumOptions.join(' / ')
    : param.type === 'number' || param.type === 'integer'
      ? t('tramos.import.manualPlaceholderNumeric')
      : t('tramos.import.manualPlaceholderText');

  const dotClass =
    source === 'column' ? 'bg-[#1F7A4D]/100'
    : source === 'manual' ? 'bg-[#1E1E1E]/60'
    : null;

  return (
    <div
      onDragOver={event => event.preventDefault()}
      onDragEnter={onDragEnter}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      className={`flex flex-col gap-1.5 rounded-lg border px-2.5 py-2 transition ${
        isOver
          ? 'border-blue-400 bg-[#1E1E1E]/6 ring-1 ring-blue-200'
          : source === 'column'
            ? 'border-emerald-300 bg-[#1F7A4D]/40'
            : source === 'manual'
              ? 'border-blue-300 bg-[#1E1E1E]/30'
              : isRequired
                ? 'border-[#B7791F]/25 bg-[#B7791F]/20'
                : 'border-dashed border-[#E8E2D8] bg-[#FFFFFF]'
      } ${isDragging ? 'opacity-60' : ''}`}
    >
      <div className="flex items-center justify-between gap-1">
        <div className="flex min-w-0 items-center gap-1.5">
          {dotClass && <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dotClass}`} />}
          <span className={`truncate text-xs font-semibold ${isRequired ? 'text-amber-800' : 'text-[#6A6A6A]'}`}>
            {param.label}
            {isRequired && <span className="ml-0.5 text-amber-600">*</span>}
          </span>
        </div>
        <span className="shrink-0 rounded bg-[#F0EDE8] px-1.5 py-0.5 font-mono text-[9px] uppercase text-[#A09A91]">
          {param.type}
        </span>
      </div>

      <div className="flex items-center gap-1">
        {columnIndex != null && header != null ? (
          <>
            <button
              type="button"
              draggable
              onDragStart={onDragStart}
              className="flex flex-1 items-center justify-between rounded-md border border-emerald-300 bg-[#FFFFFF] px-2 py-1 text-[11px] font-medium text-emerald-800 hover:bg-[#1F7A4D]/10 cursor-grab active:cursor-grabbing"
              title={t('tramos.import.dragAssignedHint')}
            >
              <span className="truncate">{header}</span>
              <span className="ml-1 font-mono text-[9px] text-emerald-500">#{Number(columnIndex) + 1}</span>
            </button>
            <button
              type="button"
              onClick={onClear}
              className="rounded p-1 text-[#6a6a6a] hover:bg-[#FFFFFF] hover:text-[#B42318]"
              title={t('tramos.import.clearColumn')}
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </>
        ) : (
          <div className="flex-1 rounded border border-dashed border-[#E8E2D8] bg-[#FCF9F5]/60 px-2 py-1 text-[10px] text-[#6a6a6a]">
            {isOver
              ? t('tramos.import.releaseToAssign')
              : isRequired
                ? t('tramos.import.requiredHint')
                : t('tramos.import.dropHere')}
          </div>
        )}
      </div>

      <div className="flex items-center gap-1.5">
        {isEnum ? (
          <select
            value={manualRaw}
            onChange={e => onManualChange(e.target.value)}
            className="w-full rounded border border-[#E8E2D8] bg-[#FFFFFF] px-2 py-1 text-[11px] text-[#6A6A6A] outline-none focus:border-blue-300 focus:ring-1 focus:ring-[#1E1E1E]/10"
          >
            <option value="">{t('tramos.import.selectOption')}</option>
            {enumOptions.map(v => (
              <option key={v} value={v}>{v}</option>
            ))}
          </select>
        ) : (
          <input
            type="text"
            value={manualRaw}
            onChange={e => onManualChange(e.target.value)}
            placeholder={manualPlaceholder}
            className="w-full rounded border border-[#E8E2D8] bg-[#FFFFFF] px-2 py-1 text-[11px] text-[#6A6A6A] outline-none focus:border-blue-300 focus:ring-1 focus:ring-[#1E1E1E]/10"
          />
        )}
      </div>

      {param.description && (
        <p className="text-[10px] text-[#6a6a6a]">{param.description}</p>
      )}

      {defaultValue !== undefined && defaultValue !== '' && (
        <div className="text-[10px] text-[#6a6a6a]">
          {t('tramos.import.defaultValue', { value: String(defaultValue) })}
        </div>
      )}
    </div>
  );
};

interface ResultPhaseProps {
  result: { created: number; failed: number; errors: Array<{ row: number; name: string; error: string }> };
}

const ResultPhase: React.FC<ResultPhaseProps> = ({ result }) => {
  const { t } = useI18n();
  return (
    <div className="px-6 py-8">
      <div className={`rounded-xl border p-4 ${result.failed === 0 ? 'border-[#1F7A4D]/25 bg-[#1F7A4D]/10' : 'border-[#B7791F]/25 bg-[#F5EDE0]'}`}>
        <div className="text-sm font-semibold text-[#1E1E1E]">
          {t('tramos.import.resultSummary', { created: result.created, failed: result.failed })}
        </div>
      </div>
      {result.errors.length > 0 && (
        <div className="mt-4 max-h-72 overflow-y-auto rounded-xl border border-[#B42318]/25 bg-[#B42318]/40">
          <div className="border-b border-[#B42318]/25 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-[#B42318]">
            {t('tramos.import.errorsTitle')}
          </div>
          <ul className="divide-y divide-red-100">
            {result.errors.map((err, idx) => (
              <li key={idx} className="px-3 py-2 text-xs text-[#B42318]">
                <span className="font-mono text-[10px] text-red-500">#{err.row}</span>{' '}
                <span className="font-semibold">{err.name}:</span> {err.error}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export default ImportTramosExcelModal;
