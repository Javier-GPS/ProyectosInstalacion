/** Popup de autoposicionado de farolas: interdistancia, distribución,
 *  retranqueo y despeje a cruces. Genera farolas a lo largo del tramo elegido. */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { placeFarolasAlong, type FarolaDistribution, type FarolaPlacement } from '../../lib/editorGeometry';
import type { LngLat } from '../../lib/editorGeometry';

const DISTRIBUTIONS: { value: FarolaDistribution; label: string }[] = [
  { value: 'bilateral_tresbolillo', label: 'Bilateral tresbolillo' },
  { value: 'unilateral_r', label: 'Unilateral derecha' },
  { value: 'unilateral_l', label: 'Unilateral izquierda' },
  { value: 'bilateral_pareado', label: 'Bilateral pareado' },
  { value: 'centrada_mediana', label: 'Centrada en mediana' },
  { value: 'mediana_compartida', label: 'Mediana compartida' },
];

export interface FarolaPlaceResult {
  items: FarolaPlacement[];
  opts: {
    spacing: number;
    clearance: number;
    setback: number;
    distribution: FarolaDistribution;
    roadHalfWidth: number;
    poleH: number;
    armLen: number;
    tilt: number;
    watts: number;
  };
}

interface Props {
  x: number;
  y: number;
  path: LngLat[];
  roadHalfWidth: number;
  label: string;
  /** Polígonos de calzadas que cruzan, para no colocar farolas sobre el asfalto. */
  obstacleRings: LngLat[][];
  onPlace: (result: FarolaPlaceResult) => void;
  onClose: () => void;
}

const field = 'mt-0.5 w-full rounded border border-salvi-line bg-white px-2 py-1.5 text-xs';

const FarolaPlacementPopup: React.FC<Props> = ({ x, y, path, roadHalfWidth, label, obstacleRings, onPlace, onClose }) => {
  const ref = useRef<HTMLDivElement>(null);
  const [spacing, setSpacing] = useState(25);
  const [distribution, setDistribution] = useState<FarolaDistribution>('bilateral_tresbolillo');
  const [setback, setSetback] = useState(1.5);
  const [clearance, setClearance] = useState(6);
  const [poleH, setPoleH] = useState(9);
  const [armLen, setArmLen] = useState(1.2);
  const [tilt, setTilt] = useState(15);
  const [watts, setWatts] = useState(60);

  const items = useMemo(() => placeFarolasAlong(path, {
    spacing, clearance, setback, distribution, roadHalfWidth, asphaltRings: obstacleRings,
  }), [path, spacing, clearance, setback, distribution, roadHalfWidth, obstacleRings]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    setTimeout(() => document.addEventListener('mousedown', onClick), 0);
    return () => document.removeEventListener('mousedown', onClick);
  }, [onClose]);

  const place = () => onPlace({ items, opts: { spacing, clearance, setback, distribution, roadHalfWidth, poleH, armLen, tilt, watts } });

  return (
    <div
      ref={ref}
      className="fixed z-50 w-72 rounded-xl bg-white shadow-xl ring-1 ring-salvi-line/50"
      style={{ left: Math.max(4, Math.min(x, window.innerWidth - 296)), top: Math.max(4, Math.min(y, window.innerHeight - 470)) }}
    >
      <div className="flex items-center justify-between border-b border-salvi-line px-3 py-2">
        <h3 className="truncate text-xs font-semibold text-salvi-black">💡 Farolas — {label}</h3>
        <button onClick={onClose} className="text-[11px] text-salvi-muted hover:text-salvi-grey">✕</button>
      </div>

      <div className="space-y-2 px-3 py-2">
        <div className="grid grid-cols-2 gap-2">
          <label className="block">
            <span className="text-[10px] font-medium text-salvi-grey">Interdistancia (m)</span>
            <input type="number" min={1} step={0.1} value={spacing} onChange={e => setSpacing(parseFloat(e.target.value) || 25)} className={field} />
          </label>
          <label className="block">
            <span className="text-[10px] font-medium text-salvi-grey">Retranqueo (m)</span>
            <input type="number" min={0} step={0.1} value={setback} onChange={e => setSetback(parseFloat(e.target.value) || 0)} className={field} />
          </label>
          <label className="block">
            <span className="text-[10px] font-medium text-salvi-grey">Despeje cruces (m)</span>
            <input type="number" min={0} step={1} value={clearance} onChange={e => setClearance(parseFloat(e.target.value) || 0)} className={field} />
          </label>
          <label className="block">
            <span className="text-[10px] font-medium text-salvi-grey">Altura poste (m)</span>
            <input type="number" min={0} step={0.5} value={poleH} onChange={e => setPoleH(parseFloat(e.target.value) || 0)} className={field} />
          </label>
          <label className="block">
            <span className="text-[10px] font-medium text-salvi-grey">Brazo (m)</span>
            <input type="number" min={0} step={0.1} value={armLen} onChange={e => setArmLen(parseFloat(e.target.value) || 0)} className={field} />
          </label>
          <label className="block">
            <span className="text-[10px] font-medium text-salvi-grey">Inclinación (°)</span>
            <input type="number" min={0} max={45} step={1} value={tilt} onChange={e => setTilt(parseFloat(e.target.value) || 0)} className={field} />
          </label>
        </div>

        <label className="block">
          <span className="text-[10px] font-medium text-salvi-grey">Distribución</span>
          <select value={distribution} onChange={e => setDistribution(e.target.value as FarolaDistribution)} className={field}>
            {DISTRIBUTIONS.map(d => <option key={d.value} value={d.value}>{d.label}</option>)}
          </select>
        </label>

        <label className="block">
          <span className="text-[10px] font-medium text-salvi-grey">Potencia (W)</span>
          <input type="number" min={0} step={5} value={watts} onChange={e => setWatts(parseFloat(e.target.value) || 0)} className={field} />
        </label>

        <p className="rounded bg-salvi-surface px-2 py-1 text-[10px] text-salvi-muted">
          {items.length} farola{items.length !== 1 ? 's' : ''} a colocar a lo largo del tramo (sin invadir cruces).
        </p>
      </div>

      <div className="flex gap-1.5 border-t border-salvi-line px-3 py-2">
        <button onClick={onClose} className="rounded border border-salvi-line px-3 py-1 text-[10px] text-salvi-muted hover:bg-salvi-surface">
          Cancelar
        </button>
        <button
          onClick={place}
          disabled={!items.length}
          className="ml-auto rounded bg-salvi-black px-3 py-1 text-[10px] text-white disabled:opacity-40"
        >
          Colocar {items.length} farolas
        </button>
      </div>
    </div>
  );
};

export default FarolaPlacementPopup;
