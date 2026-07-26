import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { X, Calculator, CheckCircle2, XCircle } from 'lucide-react';
import { useConfigStore } from '../../store/useConfigStore';
import type { FluxDetail, LDTInfo, CalculationResult } from '../../types';
import { useI18n } from '../../i18n';
import { buildCalculationRequest } from '../../lib/tramoRequest';

interface CalculatorModalProps {
  open: boolean;
  onClose: () => void;
}

interface DimOption { id: number; name: string; eficiencia?: number | null }
interface DimsData {
  gamas: DimOption[]; difusores: DimOption[]; lentes: DimOption[]; led_types: DimOption[];
  pmax_by_combo?: Record<string, number>;
}

const format = (v: number, d = 1) => v.toFixed(d);
const kW = (v: number) => v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(0);

const CalculatorModal: React.FC<CalculatorModalProps> = ({ open, onClose }) => {
  const { t } = useI18n();
  const s = useConfigStore();

  const [dims, setDims] = useState<DimsData | null>(null);
  const [catalog, setCatalog] = useState<LDTInfo[]>([]);
  const [fluxDetail, setFluxDetail] = useState<FluxDetail | null>(null);
  const [loadingInit, setLoadingInit] = useState(true);
  const [testFlux, setTestFlux] = useState('');
  const [calculating, setCalculating] = useState(false);
  const [result, setResult] = useState<CalculationResult | null>(null);
  const [calcError, setCalcError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoadingInit(true);
    setResult(null);
    setCalcError(null);
    setTestFlux('');
    Promise.all([
      fetch('/api/ldt/dimensions').then(r => r.json()),
      fetch('/api/ldt/catalog').then(r => r.json()),
    ]).then(([d, c]) => {
      setDims(d);
      setCatalog(Array.isArray(c) ? c : []);
    }).catch(console.error).finally(() => setLoadingInit(false));
  }, [open]);

  const { gama, difusor, lente, led_type, cct, cri, driverEfficiency, target_flux: tf } = s;

  const pmaxKey = useMemo(() => {
    if (!gama || !difusor || !lente) return null;
    return [gama, difusor, lente, led_type || ''].map(x => x.trim().toUpperCase()).join('|');
  }, [gama, difusor, lente, led_type]);

  const pmax = useMemo(() => {
    if (!pmaxKey || !dims?.pmax_by_combo) return null;
    const v = dims.pmax_by_combo[pmaxKey];
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
  }, [dims, pmaxKey]);

  useEffect(() => {
    if (!gama || !difusor || !lente || !led_type || !open) { setFluxDetail(null); return; }
    const ctrl = new AbortController();
    fetch('/api/ldt/flux-detail', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ gama, difusor, lente, led_type, cct, cri, target_flux: tf || undefined, driver_eficiencia: driverEfficiency }),
      signal: ctrl.signal,
    }).then(r => r.ok ? r.json() : null).then(d => setFluxDetail(d)).catch(() => {});
    return () => ctrl.abort();
  }, [gama, difusor, lente, led_type, cct, cri, tf, driverEfficiency, open]);

  const matchingLdt = useMemo(() => {
    if (!gama || !difusor || !lente) return null;
    const key = [gama, difusor, lente, led_type || ''].map(x => (x || '').trim().toUpperCase()).join('|');
    return catalog.find(i => {
      const ik = [i.gama, i.difusor, i.lente, i.led_type || ''].map(x => (x || '').trim().toUpperCase()).join('|');
      return ik === key;
    }) || null;
  }, [catalog, gama, difusor, lente, led_type]);

  const totalEff = useMemo(() => {
    if (!fluxDetail) return null;
    return fluxDetail.efficiency * driverEfficiency;
  }, [fluxDetail, driverEfficiency]);

  const geometryItems = useMemo(() => [
    ['road_width', s.road_width, 'm'],
    ['sidewalk_left', s.sidewalk_left, 'm'],
    ['sidewalk_right', s.sidewalk_right, 'm'],
    ['lanes', s.lanes, ''],
    ['arrangement', s.arrangement, ''],
    ['height', s.height, 'm'],
    ['spacing', s.spacing, 'm'],
    ['tilt', s.tilt, '°'],
    ['arm_length', s.arm_length, 'm'],
    ['lighting_class', s.lighting_class, ''],
    ['pole_offset', s.pole_offset, 'm'],
    ['mf', s.mf, ''],
  ] as const, [s]);

  const runCalculation = useCallback(async () => {
    const flux = parseFloat(testFlux.replace(',', '.'));
    if (!flux || flux <= 0) return;
    setCalculating(true);
    setCalcError(null);
    setResult(null);
    try {
      const base = buildCalculationRequest();
      const body = { ...base, target_flux: flux, power: 0 };
      const res = await fetch('/api/calculate?skip_optimization=true', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || `Error HTTP ${res.status}`);
      }
      setResult(await res.json());
    } catch (e: any) {
      setCalcError(e.message || 'Error al calcular');
    } finally {
      setCalculating(false);
    }
  }, [testFlux]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 pt-6 pb-10 backdrop-blur-sm">
      <div className="relative w-full max-w-3xl rounded-2xl border border-[#E8E2D8] bg-[#FFFFFF] shadow-2xl">
        <div className="flex items-center justify-between border-b border-[#E8E2D8] px-5 py-3">
          <h2 className="flex items-center gap-2 text-base font-bold text-[#1E1E1E]">
            <Calculator className="h-4 w-4 text-blue-500" />
            Comprobación de cálculos
          </h2>
          <button onClick={onClose} className="rounded-lg p-1.5 text-[#6a6a6a] hover:bg-[#FFFFFF] hover:text-[#6A6A6A]">
            <X className="h-4 w-4" />
          </button>
        </div>

        {loadingInit && !catalog.length ? (
          <div className="flex items-center justify-center py-16 text-sm text-[#6a6a6a]">
            <div className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
            Cargando catálogo...
          </div>
        ) : (
          <div className="space-y-4 p-5 text-sm">

            {/* 1. Geometry + 4-tuple */}
            <div className="grid grid-cols-[1fr_1fr] gap-4">
              <div className="rounded-lg border border-[#E8E2D8] bg-[#FCF9F5]/60 p-3">
                <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide text-[#A09A91]">Vía</div>
                <div className="grid grid-cols-3 gap-x-3 gap-y-0.5 text-[11px]">
                  {geometryItems.map(([label, value, unit]) => (
                    <React.Fragment key={label}>
                      <span className="text-[#A09A91]">{label.replace(/_/g, ' ')}</span>
                      <span className="font-mono font-semibold text-[#1E1E1E] text-right">
                        {typeof value === 'number' ? format(value, label === 'tilt' ? 0 : 2) : String(value)}
                      </span>
                      <span className="text-[#6a6a6a]">{unit}</span>
                    </React.Fragment>
                  ))}
                </div>
              </div>
              <div className="space-y-2">
                <div className="rounded-lg border border-[#E8E2D8] bg-[#FCF9F5]/60 p-3">
                  <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide text-[#A09A91]">4-Tupla</div>
                  <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px]">
                    <span className="text-[#A09A91]">Gama</span>
                    <span className="font-mono font-semibold text-[#1E1E1E] text-right">{gama || '—'}</span>
                    <span className="text-[#A09A91]">Difusor</span>
                    <span className="font-mono font-semibold text-[#1E1E1E] text-right">{difusor || '—'}</span>
                    <span className="text-[#A09A91]">Lente</span>
                    <span className="font-mono font-semibold text-[#1E1E1E] text-right">{lente || '—'}</span>
                    <span className="text-[#A09A91]">LED type</span>
                    <span className="font-mono font-semibold text-[#1E1E1E] text-right">{led_type || '—'}</span>
                  </div>
                </div>
                {matchingLdt && (
                  <div className="rounded-lg border border-[#E8E2D8] bg-[#FCF9F5]/60 p-3">
                    <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-[#A09A91]">LDT</div>
                    <div className="truncate text-[11px] font-medium text-[#6A6A6A]" title={matchingLdt.luminaire_name}>{matchingLdt.luminaire_name}</div>
                    <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10px] mt-1">
                      <span className="text-[#A09A91]">Flujo ref.</span>
                      <span className="font-mono text-[#6A6A6A] text-right">{kW(matchingLdt.flux)} lm</span>
                      <span className="text-[#A09A91]">Potencia ref.</span>
                      <span className="font-mono text-[#6A6A6A] text-right">{format(matchingLdt.power)} W</span>
                      <span className="text-[#A09A91]">Eficiencia</span>
                      <span className="font-mono text-[#6A6A6A] text-right">{format(matchingLdt.efficiency)} lm/W</span>
                      <span className="text-[#A09A91]">LORL</span>
                      <span className="font-mono text-[#6A6A6A] text-right">{matchingLdt.LORL}</span>
                      <span className="text-[#A09A91]">Isym</span>
                      <span className="font-mono text-[#6A6A6A] text-right">{matchingLdt.isym}</span>
                      <span className="text-[#A09A91]">CCT / CRI</span>
                      <span className="font-mono text-[#6A6A6A] text-right">{matchingLdt.cct}K / {matchingLdt.cri ?? 70}</span>
                      {pmax !== null && (
                        <><span className="text-[#A09A91]">Pmax</span><span className="font-mono text-[#6A6A6A] text-right">{format(pmax, 0)} W</span></>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* 2. Efficiency Chain (informational) */}
            {fluxDetail && (
              <div className="rounded-lg border border-[#E8E2D8] bg-[#FCF9F5]/60 p-3">
                <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide text-[#A09A91]">Cadena de rendimiento</div>
                <div className="grid grid-cols-[auto_1fr_auto] gap-x-3 gap-y-0.5 text-[11px]">
                  <span className="text-[#A09A91] col-span-2">Eficacia LED</span>
                  <span className="font-mono text-[#1E1E1E] text-right">{format(fluxDetail.led_efficacy, 1)} lm/W</span>
                  <span className="text-[#A09A91] col-span-2">Factor térmico</span>
                  <span className="font-mono text-[#1E1E1E] text-right">× {format(fluxDetail.thermal_derating, 3)}</span>
                  {fluxDetail.lente_eficiencia != null && (
                    <><span className="text-[#6a6a6a] col-span-2 pl-2">└ Lente η</span><span className="font-mono text-[#6A6A6A] text-right">× {(fluxDetail.lente_eficiencia * 100).toFixed(1)}%</span></>
                  )}
                  {fluxDetail.difusor_eficiencia != null && (
                    <><span className="text-[#6a6a6a] col-span-2 pl-2">└ Difusor η</span><span className="font-mono text-[#6A6A6A] text-right">× {(fluxDetail.difusor_eficiencia * 100).toFixed(1)}%</span></>
                  )}
                  <span className="text-[#6a6a6a] col-span-2 pl-2">└ Driver η</span>
                  <span className="font-mono text-[#6A6A6A] text-right">× {(driverEfficiency * 100).toFixed(1)}%</span>
                  <span className="col-span-2 mt-0.5 border-t border-dotted border-[#D4CEC6] pt-0.5 font-semibold text-[#1E1E1E]">Rendimiento total</span>
                  <span className="mt-0.5 border-t border-dotted border-[#D4CEC6] pt-0.5 font-mono font-semibold text-[#1E1E1E] text-right">{(totalEff || 0).toFixed(1)} lm/W</span>
                </div>
              </div>
            )}

            {/* 3. EN 13201 Calculator */}
            <div className="rounded-xl border-2 border-blue-200 bg-[#1E1E1E]/60 p-4">
              <div className="mb-2 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-[#333333]">
                <Calculator className="h-3.5 w-3.5" />
                Calculadora EN 13201
              </div>
              <p className="mb-3 text-[11px] text-[#A09A91]">
                Introduce el flujo final de la luminaria (lúmenes reales de salida) y ejecuta la simulación CIE 140 con exactamente ese valor.
              </p>

              <div className="flex items-end gap-3">
                <div className="flex-1">
                  <label className="mb-1 block text-[11px] font-medium text-[#6A6A6A]">Flujo final (lm)</label>
                  <input
                    type="text" inputMode="decimal"
                    value={testFlux}
                    onChange={e => { setTestFlux(e.target.value); setResult(null); setCalcError(null); }}
                    placeholder={fluxDetail ? `ej. ${fluxDetail.flux.toFixed(0)}` : '10000'}
                    className="w-full rounded-lg border border-blue-300 bg-[#FFFFFF] px-3 py-2.5 text-sm font-mono font-semibold text-[#1E1E1E] shadow-sm outline-none focus:border-[#1E1E1E] focus:ring-2 focus:ring-blue-200"
                  />
                </div>
                <button
                  onClick={() => fluxDetail && setTestFlux(fluxDetail.flux.toFixed(0))}
                  className="mb-[1px] rounded-lg border border-blue-300 bg-[#FFFFFF] px-3 py-2.5 text-[11px] font-semibold text-[#333333] hover:bg-[#1E1E1E]/6"
                >Valor ref.</button>
                <button
                  onClick={runCalculation}
                  disabled={calculating || !testFlux.trim()}
                  className="mb-[1px] rounded-lg bg-[#1E1E1E] px-5 py-2.5 text-sm font-bold text-white shadow-sm hover:bg-[#333333] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {calculating ? (
                    <span className="flex items-center gap-2"><span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" /> Calculando...</span>
                  ) : 'Calcular'}
                </button>
              </div>

              {calcError && (
                <div className="mt-3 rounded-lg border border-[#B42318]/25 bg-[#FDECEA] p-2.5 text-xs text-[#B42318]">{calcError}</div>
              )}

              {result && result.criteria && (
                <div className="mt-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-bold ${result.compliant ? 'bg-[#1F7A4D]/10 text-[#1F7A4D]' : 'bg-[#FDECEA] text-[#B42318]'}`}>
                      {result.compliant ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
                      {result.compliant ? 'CUMPLE' : 'NO CUMPLE'} EN 13201 · {result.mode}
                    </span>
                    <span className="text-xs text-[#6a6a6a]">Flujo: {kW((result as any).luminaire?.flux || 0)} lm</span>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                    {([
                      ['Lavg', result.Lavg, 'cd/m²', 2],
                      ['Uo', result.Uo, '', 2],
                      ['Ul/UI', result.Ul, '', 2],
                      ['TI', result.TI, '%', 1],
                      ['SR', result.SR, '', 2],
                      ['Em', result.Eavg, 'lux', 1],
                    ] as const).filter(([_, v]) => v != null).map(([label, value, unit, decimals]) => {
                      const criterion = result.criteria?.find(c => c.name.toLowerCase().includes(label.toLowerCase().replace('/', '')));
                      const passed = criterion ? criterion.passed : true;
                      const required = criterion?.required;
                      return (
                        <div key={label} className={`rounded-lg border p-2.5 ${passed ? 'border-emerald-100 bg-[#1F7A4D]/40' : 'border-red-100 bg-[#B42318]/40'}`}>
                          <div className="text-[10px] font-semibold uppercase tracking-wide text-[#A09A91]">{label}</div>
                          <div className={`mt-0.5 font-mono text-lg font-bold ${passed ? 'text-[#1F7A4D]' : 'text-[#B42318]'}`}>
                            {typeof value === 'number' ? (value as number).toFixed(decimals as number) : '—'}
                          </div>
                          {required != null && (
                            <div className="text-[10px] text-[#6a6a6a]">
                              req. {typeof required === 'number' ? (required as number).toFixed(decimals as number) : required} {unit}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="mt-2 text-[10px] text-[#6a6a6a] leading-relaxed">
                Ejecuta el motor CIE 140 / EN 13201 con el flujo exacto indicado (sin optimización automática).
                El flujo se usa directamente como escala fotométrica. No se aplica ninguna deducción de eficiencia.
              </div>
            </div>

          </div>
        )}
      </div>
    </div>
  );
};

export default CalculatorModal;
