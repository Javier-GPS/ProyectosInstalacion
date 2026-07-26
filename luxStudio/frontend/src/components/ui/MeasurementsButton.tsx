import React, { useMemo, useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { useI18n } from '../../i18n';
import type { MeasurementGrid, MeasurementResponse } from '../../types';

interface MeasurementsButtonProps {
  config?: any;
  loadConfig?: () => Promise<any>;
  disabled?: boolean;
  tramoId?: number;
  compact?: boolean;
}

const fmt = (value: number | undefined, digits = 2) => {
  if (value === undefined || value === null || Number.isNaN(value)) return '-';
  return value.toFixed(digits);
};

const displayUnit = (unit: string) => unit.replace('&#178;', '2');

const formatFlux = (value?: number | null) => {
  if (value === undefined || value === null || Number.isNaN(value)) return '-';
  return `${value.toFixed(0)} lm`;
};

const MeasurementsTable: React.FC<{ grid: MeasurementGrid }> = ({ grid }) => {
  const rows = useMemo(
    () => grid.ys.map((y, index) => ({ y, index })).reverse(),
    [grid.ys],
  );

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto rounded-lg border border-[#E8E2D8]">
        <table className="min-w-full border-collapse bg-[#FFFFFF] text-right font-mono text-xs">
          <thead>
            <tr className="border-b border-[#E8E2D8] bg-[#FCF9F5] text-[#6A6A6A]">
              <th className="sticky left-0 z-10 bg-[#FCF9F5] px-3 py-2 text-left font-semibold">m</th>
              {grid.xs.map((x, index) => (
                <th key={`${x}-${index}`} className="px-3 py-2 font-semibold">
                  {fmt(x, 3)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(({ y, index }) => (
              <tr key={`${y}-${index}`} className="odd:bg-[#FFFFFF] even:bg-[#FCF9F5]">
                <th className="sticky left-0 z-10 bg-inherit px-3 py-2 text-left font-semibold text-[#1E1E1E]">
                  {fmt(y, 3)}
                </th>
                {grid.xs.map((x, colIndex) => (
                  <td key={`${x}-${colIndex}`} className="px-3 py-2 text-[#1E1E1E]">
                    {fmt(grid.values[colIndex]?.[index], 2)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid grid-cols-2 gap-3 text-center sm:grid-cols-5">
        <div>
          <div className="text-xs font-semibold text-[#A09A91]">Eav [{displayUnit(grid.unit)}]</div>
          <div className="font-mono text-base font-semibold text-[#1E1E1E]">{fmt(grid.avg, 2)}</div>
        </div>
        <div>
          <div className="text-xs font-semibold text-[#A09A91]">Emin [{displayUnit(grid.unit)}]</div>
          <div className="font-mono text-base font-semibold text-[#1E1E1E]">{fmt(grid.min, 2)}</div>
        </div>
        <div>
          <div className="text-xs font-semibold text-[#A09A91]">Emax [{displayUnit(grid.unit)}]</div>
          <div className="font-mono text-base font-semibold text-[#1E1E1E]">{fmt(grid.max, 2)}</div>
        </div>
        <div>
          <div className="text-xs font-semibold text-[#A09A91]">u0</div>
          <div className="font-mono text-base font-semibold text-[#1E1E1E]">{fmt(grid.uniformity_avg, 3)}</div>
        </div>
        <div>
          <div className="text-xs font-semibold text-[#A09A91]">Emin / Emax</div>
          <div className="font-mono text-base font-semibold text-[#1E1E1E]">{fmt(grid.uniformity_max, 3)}</div>
        </div>
      </div>
    </div>
  );
};

const MeasurementsButton: React.FC<MeasurementsButtonProps> = ({ config, loadConfig, disabled, tramoId, compact }) => {
  const { authFetch } = useAuth();
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<MeasurementResponse | null>(null);

  const primaryGrid = data?.grids?.[data.primary] ?? data?.grids?.illuminance ?? null;
  const sidewalkRightGrid = data?.grids?.sidewalk_right ?? null;
  const sidewalkLeftGrid = data?.grids?.sidewalk_left ?? null;
  const hasSidewalks = sidewalkRightGrid || sidewalkLeftGrid;

  const loadMeasurements = async () => {
    if (disabled || (!config && !loadConfig)) return;
    setOpen(true);
    setLoading(true);
    setError(null);
    try {
      const requestConfig = config ?? await loadConfig?.();
      if (!requestConfig) throw new Error(t('errors.unknown'));
      const endpoint = tramoId ? `/api/report/measurements?tramo_id=${tramoId}` : '/api/report/measurements';
      const response = await authFetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestConfig),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || t('errors.unknown'));
      }
      setData(await response.json());
    } catch (err: any) {
      setError(err.message || t('errors.unknown'));
    } finally {
      setLoading(false);
    }
  };

  const buttonClass = compact
    ? 'inline-flex items-center gap-1 rounded-md border border-[#1E1E1E]/15 bg-[#1E1E1E]/6 px-2 py-1 text-xs font-semibold text-[#333333] hover:bg-[#1E1E1E]/20 disabled:cursor-not-allowed disabled:border-[#E8E2D8] disabled:bg-[#FFFFFF] disabled:text-[#8A847A]'
    : 'inline-flex items-center gap-1 rounded-md border border-[#E8E2D8] bg-[#FFFFFF] px-1.5 py-0.5 text-[10px] font-semibold text-[#6A6A6A] transition-colors hover:bg-[#F7F4EF] disabled:cursor-not-allowed disabled:border-[#B42318]/25 disabled:bg-[#FDECEA] disabled:text-[#B42318] disabled:line-through disabled:opacity-60';

  return (
    <>
      <button
        type="button"
        onClick={loadMeasurements}
        disabled={disabled || loading}
        title={disabled ? t('results.calculateFirstForDocuments') : t('tramos.reports.measurements')}
        className={buttonClass}
      >
        {loading ? (
          <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" opacity="0.25" />
            <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
          </svg>
        ) : (
          <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <path d="M3 9h18M3 15h18M9 3v18M15 3v18" />
          </svg>
        )}
        <span>{t('tramos.reports.measurements')}</span>
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 px-4 py-6"
          onClick={() => setOpen(false)}
        >
          <div
            className="flex max-h-full w-full max-w-6xl flex-col overflow-hidden rounded-xl bg-[#FFFFFF] shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4 border-b border-[#E8E2D8] px-5 py-4">
              <div className="min-w-0">
                <h2 className="truncate text-base font-semibold text-[#1E1E1E]">
                  {t('measurements.title')}
                </h2>
                {data && (
                  <div className="mt-1 space-y-1 text-xs text-[#A09A91]">
                    <p className="truncate">
                      {data.config.lighting_class} / {data.luminaire.luminaire_name} / {data.config.arrangement}
                    </p>
                    <p className="font-semibold text-[#6A6A6A]">
                      Flujo luminoso: {formatFlux(data.luminaire.flux)}
                    </p>
                  </div>
                )}
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-md border border-[#E8E2D8] px-2 py-1 text-xs font-semibold text-[#6A6A6A] hover:bg-[#F7F4EF]"
              >
                {t('advancedResults.close')}
              </button>
            </div>

            <div className="min-h-0 overflow-auto p-5">
              {loading ? (
                <div className="py-16 text-center text-sm text-[#A09A91]">{t('measurements.loading')}</div>
              ) : error ? (
                <div className="rounded-lg border border-[#B42318]/25 bg-[#FDECEA] p-3 text-sm text-[#B42318]">{error}</div>
              ) : primaryGrid || hasSidewalks ? (
                <div className="space-y-6">
                  {sidewalkRightGrid && (
                    <div>
                      <h3 className="mb-2 text-sm font-semibold text-[#6A6A6A]">{t('geometry.rightSidewalk')}</h3>
                      <MeasurementsTable grid={sidewalkRightGrid} />
                    </div>
                  )}
                  {primaryGrid && (
                    <div>
                      <h3 className="mb-2 text-sm font-semibold text-[#6A6A6A]">
                        {primaryGrid.title || (data?.config?.lighting_class?.startsWith('M') ? 'Luminancia' : 'Iluminancia')} — Calzada
                      </h3>
                      <MeasurementsTable grid={primaryGrid} />
                    </div>
                  )}
                  {sidewalkLeftGrid && (
                    <div>
                      <h3 className="mb-2 text-sm font-semibold text-[#6A6A6A]">{t('geometry.leftSidewalk')}</h3>
                      <MeasurementsTable grid={sidewalkLeftGrid} />
                    </div>
                  )}
                  {primaryGrid && (
                    <p className="text-xs text-[#A09A91]">
                      {t('measurements.note', {
                        unit: displayUnit(primaryGrid.unit),
                        mf: Number(data?.config?.mf ?? 1).toFixed(2),
                      })}
                    </p>
                  )}
                </div>
              ) : (
                <div className="rounded-lg border border-[#E8E2D8] bg-[#FCF9F5] p-3 text-sm text-[#A09A91]">
                  {t('measurements.empty')}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default MeasurementsButton;
