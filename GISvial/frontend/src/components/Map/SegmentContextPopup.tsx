/** Floating popup on right-click — shows segment info and inline editing. */
import React, { useEffect, useRef, useState } from 'react';
import { useGisStore, ROAD_CFG } from '../../store/useGisStore';
import type { GisPlanningInventoryTarget, GisPlanningPatch, GisLightingClass, GisDistribution } from '../../types';

const UNE_CLASSES: GisLightingClass[] = ['M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'C0', 'C1', 'C2', 'C3', 'C4', 'C5', 'P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7'];
const DISTRIBUTIONS: { value: GisDistribution; label: string }[] = [
  { value: 'unilateral_r', label: 'Unilateral derecha' },
  { value: 'unilateral_l', label: 'Unilateral izquierda' },
  { value: 'bilateral_pareado', label: 'Bilateral' },
  { value: 'bilateral_tresbolillo', label: 'Bilateral tresbolillo' },
  { value: 'centrada_mediana', label: 'Centrada en mediana' },
  { value: 'mediana_compartida', label: 'Sin luminarias (mediana compartida)' },
];

interface SegmentContextPopupProps {
  /** Screen position where to render */
  x: number;
  y: number;
  /** The target that was right-clicked */
  target: GisPlanningInventoryTarget;
  /** Road type string (e.g. 'primary') */
  roadType: string | null;
  /** Close handler */
  onClose: () => void;
}

const SegmentContextPopup: React.FC<SegmentContextPopupProps> = ({ x, y, target, roadType, onClose }) => {
  const ref = useRef<HTMLDivElement>(null);
  const planningPayload = useGisStore(s => s.planningPayload);
  const setTargetPatch = useGisStore(s => s.setTargetPatch);

  // Inherited patch from group defaults
  const inherited = roadType ? planningPayload.group_defaults[target.group_ref] || {} : {};
  // Current override for this target
  const [patch, setPatch] = useState<GisPlanningPatch>(() => planningPayload.target_overrides[target.target_ref] || {});

  const cfg = roadType ? ROAD_CFG[roadType] : undefined;
  const hasOverride = Object.keys(patch).length > 0;

  // Close on ESC or click outside
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    // Delay to avoid the same right-click from closing
    setTimeout(() => document.addEventListener('mousedown', onClick), 0);
    return () => document.removeEventListener('mousedown', onClick);
  }, [onClose]);

  // Compute effective value: own patch > inherited > undefined
  const effective = <K extends keyof GisPlanningPatch>(key: K): GisPlanningPatch[K] | undefined =>
    (key in patch) ? patch[key] : inherited[key as keyof GisPlanningPatch] as any;

  const setField = <K extends keyof GisPlanningPatch>(key: K, value: GisPlanningPatch[K] | undefined) => {
    const next = { ...patch };
    if (value === undefined) delete next[key];
    else (next as any)[key] = value;
    setPatch(next);
  };

  const lux = patch.luxParams && typeof patch.luxParams === 'object' ? patch.luxParams : {};
  const inheritedLux = inherited?.luxParams && typeof inherited.luxParams === 'object' ? inherited.luxParams : {};

  const setLuxField = (key: string, value: string | number | null | undefined) => {
    const nextLux = { ...lux };
    if (value === undefined) delete (nextLux as any)[key];
    else (nextLux as any)[key] = value;
    const next = { ...patch };
    if (Object.keys(nextLux).length) next.luxParams = nextLux;
    else delete next.luxParams;
    setPatch(next);
  };

  const save = () => {
    setTargetPatch(target.target_ref, patch);
    onClose();
  };

  // Clamp popup to viewport
  const popupX = Math.min(x, window.innerWidth - 340);
  const popupY = Math.min(y, window.innerHeight - 420);

  return (
    <div
      ref={ref}
      className="fixed z-50 w-80 rounded-xl bg-white shadow-xl ring-1 ring-salvi-line/50"
      style={{ left: Math.max(4, popupX), top: Math.max(4, popupY) }}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-salvi-line px-3 py-2">
        <h3 className="truncate text-xs font-semibold text-salvi-black">{target.name || 'Sin nombre'}</h3>
        <button onClick={onClose} className="text-[11px] text-salvi-muted hover:text-salvi-grey">✕</button>
      </div>

      {/* Info section */}
      <div className="border-b border-salvi-line/50 px-3 py-2 text-[10px] text-salvi-muted">
        <div className="flex flex-wrap gap-x-3 gap-y-1">
          <span>Tramo {target.source_index + 1}</span>
          <span>{target.length_m == null ? '—' : `${Math.round(target.length_m)} m`}</span>
          {cfg && <span>Calzada {cfg.width} m</span>}
          {roadType && <span>{cfg ? cfg.labelKey.replace('road.', '') : roadType}</span>}
        </div>
        {(!lux.sidewalkL && !lux.sidewalkR && !inheritedLux.sidewalkL && !inheritedLux.sidewalkR) ? null : (
          <div className="mt-1 flex gap-3">
            {lux.sidewalkL != null && <span>Acera I {lux.sidewalkL} m</span>}
            {lux.sidewalkR != null && <span>Acera D {lux.sidewalkR} m</span>}
            {!lux.sidewalkL && inheritedLux.sidewalkL != null && <span className="opacity-60">Acera I {inheritedLux.sidewalkL} m (tipo)</span>}
            {!lux.sidewalkR && inheritedLux.sidewalkR != null && <span className="opacity-60">Acera D {inheritedLux.sidewalkR} m (tipo)</span>}
          </div>
        )}
      </div>

      {/* Editable fields */}
      <div className="space-y-2 px-3 py-2">
        <label className="block text-[10px] text-salvi-muted">
          Clase UNE-EN 13201
          <select
            value={(effective('lighting_class') as string) || ''}
            onChange={e => setField('lighting_class', e.target.value ? e.target.value as GisLightingClass : undefined)}
            className={`mt-0.5 w-full rounded border px-2 py-1 text-[11px] ${hasOverride && 'lighting_class' in patch ? 'border-state-info' : 'border-salvi-line'}`}
          >
            <option value="">—</option>
            {UNE_CLASSES.map(v => <option key={v} value={v}>{v}</option>)}
          </select>
        </label>

        <label className="block text-[10px] text-salvi-muted">
          Interdistancia (m)
          <input
            type="number" min="0" step="0.1"
            value={(effective('spacing') as number | undefined) ?? ''}
            onChange={e => setField('spacing', e.target.value === '' ? undefined : Number(e.target.value))}
            className={`mt-0.5 w-full rounded border px-2 py-1 text-[11px] ${hasOverride && 'spacing' in patch ? 'border-state-info' : 'border-salvi-line'}`}
          />
        </label>

        <label className="block text-[10px] text-salvi-muted">
          Distribución
          <select
            value={(effective('distribution') as string) || ''}
            onChange={e => setField('distribution', e.target.value ? e.target.value as GisDistribution : undefined)}
            className={`mt-0.5 w-full rounded border px-2 py-1 text-[11px] ${hasOverride && 'distribution' in patch ? 'border-state-info' : 'border-salvi-line'}`}
          >
            <option value="">—</option>
            {DISTRIBUTIONS.map(d => <option key={d.value} value={d.value}>{d.label}</option>)}
          </select>
        </label>

        <details>
          <summary className="cursor-pointer text-[10px] font-medium text-salvi-grey">Parámetros de vía</summary>
          <div className="mt-1.5 grid grid-cols-2 gap-2">
            {[
              { key: 'poleH', label: 'Altura poste (m)', type: 'number' },
              { key: 'armLen', label: 'Brazo (m)', type: 'number' },
              { key: 'setback', label: 'Retranqueo (m)', type: 'number' },
              { key: 'tilt', label: 'Inclinación (°)', type: 'number' },
              { key: 'sidewalkL', label: 'Acera I (m)', type: 'number' },
              { key: 'sidewalkR', label: 'Acera D (m)', type: 'number' },
              { key: 'medianW', label: 'Mediana (m)', type: 'number' },
              { key: 'maintFactor', label: 'Factor mant.', type: 'number' },
              { key: 'power', label: 'Potencia (W)', type: 'number' },
              { key: 'colorTemp', label: 'Temp. color (K)', type: 'number' },
              { key: 'cri', label: 'CRI', type: 'number' },
            ].map(f => {
              const own = (lux as any)[f.key] !== undefined;
              const inheritedVal = (inheritedLux as any)[f.key];
              const value = own ? (lux as any)[f.key] : inheritedVal ?? '';
              return (
                <label key={f.key} className="text-[9px] text-salvi-muted">
                  {f.label}
                  <input
                    type={f.type} min={0}
                    value={value}
                    onChange={e => setLuxField(f.key, e.target.value === '' ? undefined : f.type === 'number' ? Number(e.target.value) : e.target.value)}
                    className={`mt-0.5 w-full rounded border px-1.5 py-1 text-[10px] ${own ? 'border-state-info' : 'border-salvi-line'}`}
                  />
                </label>
              );
            })}
          </div>
        </details>
      </div>

      {/* Footer: save / reset */}
      <div className="flex gap-1.5 border-t border-salvi-line px-3 py-2">
        {hasOverride && (
          <button onClick={() => { setPatch({}); }} className="rounded border border-salvi-line px-2 py-1 text-[10px] text-salvi-muted hover:bg-salvi-surface">
            Restablecer
          </button>
        )}
        <button onClick={save} className="ml-auto rounded bg-salvi-black px-3 py-1 text-[10px] text-white">
          Guardar
        </button>
      </div>
    </div>
  );
};

export default SegmentContextPopup;
