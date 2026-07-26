import React, { useState } from 'react';
import { useConfigStore } from '../../store/useConfigStore';
import type { ArrangementType, LightingClass, PavementType, PoleSide, RoadElement } from '../../types';
import EditableSlider from '../ui/EditableSlider';
import { useI18n } from '../../i18n';

const arrangements: { value: ArrangementType; labelKey: string }[] = [
  { value: 'Lineal', labelKey: 'unilateral' },
  { value: 'Bilateral', labelKey: 'bilateral' },
  { value: 'Bilateral Alternada', labelKey: 'staggered' },
  { value: 'Central Doble', labelKey: 'centralTwin' },
];

type Props = { embedded?: boolean };

const SEL = 'rounded-md border border-[#D4CEC6] bg-[#FFFFFF] px-2.5 py-1.5 text-xs font-medium text-[#6A6A6A] shadow-sm focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-200/50 cursor-pointer appearance-none bg-[url(\'data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2212%22%20height%3D%2212%22%3E%3Cpath%20d%3D%22M2%204l4%204%204-4%22%20fill%3D%22none%22%20stroke%3D%22%2394a3b8%22%20stroke-width%3D%221.5%22%20stroke-linecap%3D%22round%22%2F%3E%3C%2Fsvg%3E\')] bg-[length:14px] bg-[right_6px_center] bg-no-repeat pr-7';

function ElementRow({ el, index, total, onUpdate, onRemove, onMove }: {
  el: RoadElement; index: number; total: number;
  onUpdate: (idx: number, p: Partial<RoadElement>) => void;
  onRemove: (idx: number) => void;
  onMove: (from: number, to: number) => void;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [over, setOver] = useState(false);
  const isCw = el.type === 'carriageway';
  const minW = isCw ? 2.5 : 0.5;
  const maxW = isCw ? 25 : 10;
  const badgeCls = isCw ? 'text-violet-700 bg-violet-50 ring-violet-200' : 'text-teal-700 bg-teal-50 ring-teal-200';

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); const f = parseInt(e.dataTransfer.getData('text/plain'), 10); if (!isNaN(f) && f !== index) onMove(f, index); }}
      className={`rounded-lg border transition-all duration-150 ${over ? 'border-violet-300 bg-violet-50/50 shadow-sm' : open ? 'border-violet-200 bg-[#FFFFFF] shadow-sm' : 'border-[#E8E2D8] bg-[#FFFFFF] hover:border-violet-200 hover:shadow-sm'}`}
    >
      <div className="flex items-center gap-2 px-3 py-2 text-xs cursor-pointer" onClick={() => setOpen(!open)}>
        <span draggable
          onDragStart={(e) => { e.stopPropagation(); e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', String(index)); }}
          className="text-[#8A847A] hover:text-violet-400 cursor-grab active:cursor-grabbing text-base leading-none select-none"
          onClick={(e) => e.stopPropagation()}>⠿</span>
        <span className="font-semibold text-[#6A6A6A] shrink-0">
          <span className={isCw ? 'text-violet-600' : 'text-teal-600'}>{isCw ? 'RD' : 'SW'}</span>
          <span className="text-[#6a6a6a] ml-0.5">{index + 1}</span>
        </span>
        <span className="font-mono font-medium text-[#1E1E1E] tabular-nums">{el.width.toFixed(1)}<span className="text-[#6a6a6a] ml-0.5">m</span></span>
        <span className={`inline-flex items-center rounded-md px-2 py-0.5 font-semibold ring-1 ${badgeCls}`}>
          {isCw ? el.lighting_class ?? 'M3' : el.pedestrian_class ?? 'P4'}
        </span>
        {isCw && <span className="text-[#6a6a6a] font-mono text-[11px]">{el.lanes ?? 2}c</span>}
        <span className="ml-auto flex items-center gap-0.5" onClick={(e) => e.stopPropagation()}>
          <button onClick={() => setOpen(!open)} className="rounded p-1.5 text-[#6a6a6a] hover:text-violet-500 hover:bg-violet-50 transition-colors leading-none">{open ? '▾' : '▸'}</button>
          {index > 0 && <button onClick={() => onMove(index, index - 1)} className="rounded p-1.5 text-[#6a6a6a] hover:text-violet-500 hover:bg-violet-50 transition-colors leading-none">↑</button>}
          {index < total - 1 && <button onClick={() => onMove(index, index + 1)} className="rounded p-1.5 text-[#6a6a6a] hover:text-violet-500 hover:bg-violet-50 transition-colors leading-none">↓</button>}
          <button onClick={() => onRemove(index)} className="rounded p-1.5 text-red-300 hover:text-red-500 hover:bg-[#B42318]/15 transition-colors leading-none">✕</button>
        </span>
      </div>
      {open && (
        <div className="mx-3 mb-3 p-3 rounded-lg bg-[#FCF9F5] border border-[#E8E2D8] space-y-2.5">
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-semibold text-[#A09A91] w-10 shrink-0">{t('geometry.widthLabel')}</span>
            <input type="range" min={minW} max={maxW} step={0.5} value={el.width}
              onChange={(e) => onUpdate(index, { ...el, width: parseFloat(e.target.value) })}
              onClick={(e) => e.stopPropagation()}
              className="w-24 h-1.5 accent-violet-500 cursor-pointer" />
            <input type="number" min={minW} max={maxW} step={0.1} value={el.width}
              onChange={(e) => onUpdate(index, { ...el, width: parseFloat(e.target.value) || el.width })}
              onClick={(e) => e.stopPropagation()}
              className="w-10 rounded border border-[#D4CEC6] bg-[#FFFFFF] px-1 py-1 text-xs font-mono font-medium text-[#6A6A6A] text-right focus:border-violet-400 focus:outline-none focus:ring-1 focus:ring-violet-200 [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none" />
            <span className="text-xs text-[#6a6a6a]">m</span>
          </div>
          {isCw ? (
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5">
                <span className="text-xs font-semibold text-[#A09A91] shrink-0">{t('geometry.lanesLabel')}</span>
                <select value={el.lanes ?? 2} onChange={(e) => onUpdate(index, { ...el, lanes: parseInt(e.target.value) })} onClick={(e) => e.stopPropagation()} className={SEL}>
                  {[1, 2, 3, 4, 5, 6].map(n => <option key={n} value={n}>{n}</option>)}
                </select>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-xs font-semibold text-[#A09A91] shrink-0">{t('geometry.classLabel')}</span>
                <select value={el.lighting_class ?? 'M3'} onChange={(e) => onUpdate(index, { ...el, lighting_class: e.target.value })} onClick={(e) => e.stopPropagation()} className={SEL}>
                  {['M1','M2','M3','M4','M5','M6'].map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-semibold text-[#A09A91] shrink-0">{t('geometry.classLabel')}</span>
              <select value={el.pedestrian_class ?? 'P4'} onChange={(e) => onUpdate(index, { ...el, pedestrian_class: e.target.value })} onClick={(e) => e.stopPropagation()} className={SEL}>
                {['P1','P2','P3','P4','P5','P6','P7'].map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const GeometryPanel: React.FC<Props> = ({ embedded = false }) => {
  const { t } = useI18n();
  const {
    roadElements, addRoadElement, removeRoadElement, updateRoadElement, moveRoadElement,
    arrangement, setArrangement, pole_side, setPoleSide,
    spacing, setSpacing, pole_offset, setPoleOffset,
    pavement, setPavement, mf, setMf,
  } = useConfigStore();

  const total = roadElements.reduce((s, e) => s + e.width, 0);

  const inner = (
    <div className={embedded ? 'space-y-2' : 'p-4 space-y-4'}>
      {/* Disposición */}
      <div className="rounded-xl border border-[#E8E2D8] bg-[#FFFFFF] p-4 shadow-sm">
        <h4 className="mb-3 text-xs font-bold uppercase tracking-wider text-[#6a6a6a]">{t('geometry.arrangement')}</h4>
        <div className="grid grid-cols-4 gap-1.5 mb-3">
          {arrangements.map(a => (
            <button key={a.value} onClick={() => setArrangement(a.value)}
              className={`rounded-lg px-2 py-2 text-xs font-semibold text-center leading-tight border transition-all ${arrangement === a.value ? 'bg-violet-600 text-white border-violet-500 shadow-sm' : 'bg-[#FFFFFF] text-[#6A6A6A] border-[#E8E2D8] hover:bg-violet-50 hover:border-violet-200'}`}>
              {t(`arrangement.${a.labelKey}`)}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3 mb-3">
          <span className="text-xs font-medium text-[#6A6A6A]">{t('geometry.luminaireSidewalk')}</span>
          <div className="flex gap-1.5">
            {([['left', t('geometry.leftSidewalkOption')], ['right', t('geometry.rightSidewalkOption')]] as [PoleSide, string][]).map(([v, lbl]) => (
              <button key={v} onClick={() => setPoleSide(v)} disabled={arrangement !== 'Lineal'}
                className={`rounded-lg px-4 py-1.5 text-xs font-semibold transition-all ${pole_side === v ? 'bg-violet-600 text-white shadow-sm' : 'bg-[#FFFFFF] text-[#6A6A6A] border border-[#E8E2D8] hover:bg-violet-50'} ${arrangement !== 'Lineal' ? 'opacity-30 cursor-not-allowed' : ''}`}>
                {lbl}
              </button>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <EditableSlider label={t('geometry.spacing')} value={spacing} min={10} max={60} step={1} unit="m" decimals={1} onChange={setSpacing} dense labelClassName="text-xs font-semibold text-[#A09A91]" />
          <EditableSlider label={t('geometry.poleOffset')} value={pole_offset} min={0} max={3} step={0.05} unit="m" decimals={2} onChange={setPoleOffset} marks={['0.00', '3.00']} dense labelClassName="text-xs font-semibold text-[#A09A91]" />
        </div>
      </div>

      {/* Sección transversal */}
      <div className="rounded-xl border border-[#E8E2D8] bg-[#FFFFFF] p-4 shadow-sm">
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-xs font-bold uppercase tracking-wider text-[#6a6a6a]">{t('geometry.crossSection')}</h4>
          <span className="font-mono text-xs text-[#6a6a6a]"><span className="font-semibold text-[#6A6A6A]">{total.toFixed(1)}</span> m</span>
        </div>

        <div className="mb-3 rounded-lg bg-[#FFFFFF] p-2 shadow-inner">
          <div className="flex h-4 w-full overflow-hidden rounded">
            {roadElements.map((el, i) => {
              const p = total > 0 ? (el.width / total) * 100 : 0;
              return (
                <div key={i}
                  className={`relative h-full ${el.type === 'carriageway' ? 'bg-violet-500' : 'bg-teal-400'} ${i > 0 ? 'border-l border-white/70' : ''} flex items-center justify-center transition-all`}
                  style={{ width: `${p}%`, minWidth: p > 0 ? 4 : 0 }}
                >
                  {p > 15 && <span className="text-[10px] font-bold text-white drop-shadow-sm">{el.width.toFixed(1)}</span>}
                </div>
              );
            })}
          </div>
          <div className="flex justify-between mt-1.5 text-[10px] text-[#6a6a6a] font-mono">
            <span>0 m</span>
            <span>{(total / 2).toFixed(1)} m</span>
            <span>{total.toFixed(1)} m</span>
          </div>
        </div>

        <div className="flex gap-1.5 mb-3">
          <button onClick={() => addRoadElement({ type: 'sidewalk', width: 1.5, pedestrian_class: 'P4' })}
            className="rounded-lg px-3 py-1.5 text-xs font-semibold text-teal-600 bg-teal-50 border border-teal-200 hover:bg-teal-100 transition-all shadow-sm">+ Acera</button>
          <button onClick={() => addRoadElement({ type: 'carriageway', width: 7, lanes: 2, lighting_class: 'M3' })}
            className="rounded-lg px-3 py-1.5 text-xs font-semibold text-violet-600 bg-violet-50 border border-violet-200 hover:bg-violet-100 transition-all shadow-sm">+ Calzada</button>
        </div>

        <div className="space-y-1.5">
          {roadElements.map((el, i) => (
            <ElementRow key={i} el={el} index={i} total={roadElements.length}
              onUpdate={updateRoadElement} onRemove={removeRoadElement} onMove={moveRoadElement} />
          ))}
        </div>
      </div>

      {/* Pavimento */}
      <div className="rounded-xl border border-[#E8E2D8] bg-[#FFFFFF] p-4 shadow-sm">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-[#6a6a6a]">{t('geometry.asphalt')}</h4>
            <div className="grid grid-cols-2 gap-1.5">
              {(['R1', 'R2', 'R3', 'R4'] as PavementType[]).map(r => (
                <button key={r} onClick={() => setPavement(r)}
                  className={`rounded-lg py-2 text-xs font-semibold transition-all shadow-sm ${pavement === r ? 'bg-violet-600 text-white' : 'bg-[#FFFFFF] text-[#6A6A6A] border border-[#E8E2D8] hover:bg-violet-50'}`}>
                  {r}
                </button>
              ))}
            </div>
          </div>
          <EditableSlider label={t('geometry.maintenance')} value={mf} min={0.5} max={1} step={0.01} decimals={2} onChange={setMf} marks={['0.50', '1.00']} dense labelClassName="text-xs font-semibold text-[#A09A91]" />
        </div>
      </div>
    </div>
  );

  if (embedded) return inner;
  return (
    <div className="bg-[#FFFFFF] rounded-xl border border-[#E8E2D8] shadow-sm overflow-hidden">
      <div className="flex items-center justify-between gap-2 border-b border-[#E8E2D8] bg-[#FCF9F5] px-3 py-2">
        <h3 className="truncate font-semibold text-[#6A6A6A] text-sm flex items-center gap-2">
          <svg className="w-4 h-4 text-violet-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="3" x2="9" y2="21"/></svg>
          {t('geometry.title')}
        </h3>
      </div>
      {inner}
    </div>
  );
};

export default GeometryPanel;
