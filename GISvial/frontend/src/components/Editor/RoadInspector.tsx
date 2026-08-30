/** Inspector de tramo (vía) en el editor de ciudad.
 *  Al hacer clic sobre una calzada se editan las características que corrigen
 *  errores de OSM: anchura, carriles, aceras, mediana, doble calzada... */
import React from 'react';
import { useGisStore, ROAD_CFG } from '../../store/useGisStore';
import { effectivePatch, applyRoadOverrides, ROAD_CHAR_KEYS } from '../../lib/planningOverrides';
import { targetDisplayLabel } from '../../lib/roadNaming';
import SegmentGeometryInfo from '../Map/SegmentGeometryInfo';
import type { GisPlanningPatch } from '../../types';

const Num = ({ label, value, step = 0.1, onSet }: { label: string; value: number | ''; step?: number; onSet: (v: string | undefined) => void }) => (
  <label className="block">
    <span className="text-[10px] font-medium text-salvi-grey">{label}</span>
    <input
      type="number" step={step} min={0}
      value={value}
      onChange={e => onSet(e.target.value === '' ? undefined : e.target.value)}
      className="mt-1 w-full rounded border border-salvi-line bg-white px-2 py-1.5 text-xs"
    />
  </label>
);

const Check = ({ label, checked, onToggle }: { label: string; checked: boolean; onToggle: (v: boolean) => void }) => (
  <label className="flex items-center gap-2 text-xs text-salvi-grey">
    <input type="checkbox" checked={checked} onChange={e => onToggle(e.target.checked)} className="cursor-pointer" />
    {label}
  </label>
);

const RoadInspector: React.FC = () => {
  const ref = useGisStore(s => s.editorRoadRef);
  const inventory = useGisStore(s => s.activePlanningInventory);
  const payload = useGisStore(s => s.planningPayload);
  const setMergeTargetPatches = useGisStore(s => s.setMergeTargetPatches);
  const setTargetPatch = useGisStore(s => s.setTargetPatch);
  const setEditorRoadRef = useGisStore(s => s.setEditorRoadRef);

  const baseTarget = ref ? inventory?.targets.find(t => t.target_ref === ref) : undefined;
  if (!ref || !baseTarget) return null;

  const patch = payload.target_overrides[ref] || {};
  const effective = applyRoadOverrides(baseTarget, effectivePatch(payload, baseTarget));
  const groupTypes = new Map((inventory?.groups || []).map(g => [g.group_ref, g.road_type]));
  const roadType = groupTypes.get(baseTarget.group_ref) || baseTarget.highway || '';
  const cfg = roadType ? ROAD_CFG[roadType] : undefined;

  const has = (k: string) => patch[k as keyof GisPlanningPatch] !== undefined;
  const setField = (key: keyof GisPlanningPatch, value: string | number | boolean | undefined) =>
    setMergeTargetPatches([ref], { [key]: value } as GisPlanningPatch);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-salvi-line px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="text-lg">🛣</span>
          <span className="truncate text-sm font-semibold text-salvi-black">{targetDisplayLabel(baseTarget)}</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setTargetPatch(ref, {})}
            className="rounded border border-salvi-line px-2 py-1 text-[10px] text-salvi-muted hover:bg-salvi-surface"
          >
            Restablecer
          </button>
          <button
            onClick={() => setEditorRoadRef(null)}
            title="Cerrar"
            className="rounded p-1 text-[11px] text-salvi-muted hover:bg-salvi-surface hover:text-salvi-grey"
          >
            ✕
          </button>
        </div>
      </div>

      <div className="gis-scroll flex-1 space-y-3 overflow-y-auto p-3">
        <SegmentGeometryInfo target={effective} />

        <div>
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-salvi-muted">
            Corregir geometría
            {cfg && <span className="ml-1 normal-case text-salvi-grey/70">({cfg.labelKey.replace('road.', '')})</span>}
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Num label="Anchura calzada (m)" value={effective.estWidth ?? ''} step={0.1} onSet={v => setField('estWidth', v === undefined ? undefined : parseFloat(v))} />
            <Num label="Carriles" value={effective.lanes ?? ''} step={1} onSet={v => setField('lanes', v === undefined ? undefined : Math.max(0, parseInt(v, 10) || 0))} />
            <Num label="Acera izquierda (m)" value={effective.sidewalkWidthLeft ?? ''} step={0.1} onSet={v => setField('sidewalkWidthLeft', v === undefined ? undefined : parseFloat(v))} />
            <Num label="Acera derecha (m)" value={effective.sidewalkWidthRight ?? ''} step={0.1} onSet={v => setField('sidewalkWidthRight', v === undefined ? undefined : parseFloat(v))} />
            <Num label="Ancho mediana (m)" value={effective.medianWidth ?? ''} step={0.1} onSet={v => setField('medianWidth', v === undefined ? undefined : parseFloat(v))} />
            <Num label="Límite (km/h)" value={effective.maxspeed ?? ''} step={5} onSet={v => setField('maxspeed', v === undefined ? undefined : parseInt(v, 10) || 0)} />
          </div>
          <div className="mt-2 space-y-1">
            <Check label="Doble calzada" checked={!!effective.dual} onToggle={v => setField('dual', v)} />
            <Check label="Con mediana" checked={!!effective.median} onToggle={v => setField('median', v)} />
          </div>
        </div>

        <div className="space-y-1 border-t border-salvi-line/60 pt-2">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-salvi-muted">Cambios aplicados</div>
          {Object.keys(patch).length === 0 ? (
            <p className="text-[10px] text-salvi-muted">Sin correcciones. Muestra los valores de OSM/estimados.</p>
          ) : (
            <div className="flex flex-wrap gap-1">
              {ROAD_CHAR_KEYS.filter(k => has(k)).map(k => (
                <span key={k} className="rounded-full bg-[#FDECEA] px-1.5 py-0.5 text-[9px] text-[#B42318]">{k}</span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default RoadInspector;
