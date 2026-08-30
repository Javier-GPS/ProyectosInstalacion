import React, { useState } from 'react';
import { useI18n } from '../../i18n';
import { useGisStore } from '../../store/useGisStore';
import { getEditorType } from '../../lib/editorObjects';
import type { EditorObject } from '../../lib/editorObjects';

interface Props {
  objects: EditorObject[];
}

const EditorInspector: React.FC<Props> = ({ objects }) => {
  const { t } = useI18n();
  const zoneId = useGisStore(s => s.editorZoneId);
  const updateEditorObject = useGisStore(s => s.updateEditorObject);
  const updateEditorObjects = useGisStore(s => s.updateEditorObjects);
  const removeEditorObjects = useGisStore(s => s.removeEditorObjects);
  const selectEditorObjects = useGisStore(s => s.selectEditorObjects);
  const editorAlign = useGisStore(s => s.editorAlign);
  const setEditorAlign = useGisStore(s => s.setEditorAlign);
  const editorPlaceOffset = useGisStore(s => s.editorPlaceOffset);
  const setEditorPlaceOffset = useGisStore(s => s.setEditorPlaceOffset);

  const types = [...new Set(objects.map(o => o.type))];
  const [tab, setTab] = useState(types[0] || '');
  const activeType = types.includes(tab) ? tab : types[0] || '';
  const group = objects.filter(o => o.type === activeType);

  const setNum = (key: keyof EditorObject, value: string, ids: string[]) => {
    const n = parseFloat(value);
    if (!Number.isNaN(n) && zoneId) updateEditorObjects(zoneId, ids, { [key]: n } as Partial<EditorObject>);
  };

  const renderPanel = (def: ReturnType<typeof getEditorType>) => {
    const ids = group.map(o => o.id);
    const single = group.length === 1;
    const obj = group[0];
    const setAttr = (akey: string, value: string | number) =>
      zoneId && updateEditorObjects(zoneId, ids, { attrs: { ...(obj?.attrs || {}), [akey]: value } });

    return (
      <div className="flex h-full flex-col">
        <div className="flex items-center justify-between border-b border-salvi-line px-3 py-2">
          <div className="flex items-center gap-2">
            <span className="text-lg">{def?.icon}</span>
            <span className="text-sm font-semibold text-salvi-black">{t(def?.labelKey || activeType)}</span>
            <span className="rounded-full bg-salvi-surface px-1.5 text-[10px] text-salvi-muted">{group.length}</span>
          </div>
          <button
            onClick={() => zoneId && removeEditorObjects(zoneId, ids)}
            className="rounded border border-[#B42318]/30 px-2 py-1 text-xs font-semibold text-[#B42318] hover:bg-[#FDECEA]"
          >
            {t('editor.delete')}
          </button>
        </div>

        <div className="gis-scroll flex-1 space-y-3 overflow-y-auto p-3">
          {single && obj && (
            <div className="rounded border border-salvi-line/70 bg-salvi-surface/40 p-2">
              <label className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wide text-salvi-muted">
                <input
                  type="checkbox"
                  checked={editorAlign}
                  onChange={e => setEditorAlign(e.target.checked)}
                  className="cursor-pointer"
                />
                {t('editor.alignToRoad')}
              </label>
              <p className="mt-1 text-[9px] text-salvi-muted">{t('editor.alignHint')}</p>
              <label className="mt-2 block">
                <span className="text-[10px] font-medium text-salvi-grey">{t('editor.offsetFromRoad')}</span>
                <input
                  type="number" min={0} step={0.5}
                  value={editorPlaceOffset}
                  onChange={e => setEditorPlaceOffset(parseFloat(e.target.value) || 0)}
                  className="mt-1 w-full rounded border border-salvi-line bg-white px-2 py-1.5 text-xs"
                />
              </label>
            </div>
          )}

          {single && obj && (
            <div>
              <label className="text-[10px] font-semibold uppercase tracking-wide text-salvi-muted">{t('editor.label')}</label>
              <input
                value={obj.label ?? ''}
                onChange={e => zoneId && updateEditorObject(zoneId, obj.id, { label: e.target.value })}
                placeholder={t(def?.labelKey || activeType)}
                className="mt-1 w-full rounded border border-salvi-line bg-white px-2 py-1.5 text-xs"
              />
            </div>
          )}

          <div className="grid grid-cols-2 gap-2">
            <NumberField label={t('editor.width')} value={obj?.width ?? 0} step={0.1} min={0} onChange={v => setNum('width', v, ids)} />
            <NumberField label={t('editor.length')} value={obj?.length ?? 0} step={0.1} min={0} onChange={v => setNum('length', v, ids)} />
            <NumberField label={t('editor.height')} value={obj?.height ?? 0} step={0.1} min={0} onChange={v => setNum('height', v, ids)} />
            <NumberField label={t('editor.rotation')} value={obj?.rotation ?? 0} step={5} onChange={v => setNum('rotation', v, ids)} />
          </div>

          <div>
            <label className="text-[10px] font-semibold uppercase tracking-wide text-salvi-muted">{t('editor.color')}</label>
            <div className="mt-1 flex items-center gap-2">
              <input
                type="color"
                value={obj?.color || '#000000'}
                onChange={e => zoneId && updateEditorObjects(zoneId, ids, { color: e.target.value })}
                className="h-8 w-10 cursor-pointer rounded border border-salvi-line"
              />
              <input
                value={obj?.color || ''}
                onChange={e => zoneId && updateEditorObjects(zoneId, ids, { color: e.target.value })}
                className="w-full rounded border border-salvi-line bg-white px-2 py-1.5 text-xs"
              />
            </div>
          </div>

          {def?.attrs.length ? (
            <div className="space-y-2 border-t border-salvi-line/60 pt-2">
              <div className="text-[10px] font-semibold uppercase tracking-wide text-salvi-muted">{t('editor.properties')}</div>
              {def.attrs.map(attr => (
                <div key={attr.key}>
                  <label className="text-[10px] font-medium text-salvi-grey">{t(attr.labelKey)}</label>
                  {attr.type === 'number' && (
                    <input
                      type="number" min={attr.min} max={attr.max} step={attr.step}
                      value={Number(obj?.attrs?.[attr.key] ?? attr.default)}
                      onChange={e => setAttr(attr.key, parseFloat(e.target.value) || 0)}
                      className="mt-1 w-full rounded border border-salvi-line bg-white px-2 py-1.5 text-xs"
                    />
                  )}
                  {attr.type === 'text' && (
                    <input
                      value={String(obj?.attrs?.[attr.key] ?? '')}
                      onChange={e => setAttr(attr.key, e.target.value)}
                      className="mt-1 w-full rounded border border-salvi-line bg-white px-2 py-1.5 text-xs"
                    />
                  )}
                  {attr.type === 'select' && (
                    <select
                      value={String(obj?.attrs?.[attr.key] ?? attr.default)}
                      onChange={e => setAttr(attr.key, e.target.value)}
                      className="mt-1 w-full rounded border border-salvi-line bg-white px-2 py-1.5 text-xs"
                    >
                      {attr.options?.map(o => <option key={o.value} value={o.value}>{t(o.labelKey)}</option>)}
                    </select>
                  )}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    );
  };

  return (
    <div className="flex h-full flex-col">
      {types.length > 1 && (
        <div className="flex gap-1 border-b border-salvi-line bg-salvi-surface/50 p-1.5">
          {types.map(ty => {
            const c = getEditorType(ty);
            const isActive = ty === activeType;
            return (
              <button
                key={ty}
                onClick={() => setTab(ty)}
                className={`flex-1 rounded px-1 py-1 text-[11px] font-medium ${isActive ? 'bg-white text-salvi-black shadow-sm' : 'text-salvi-grey hover:bg-white/60'}`}
              >
                {c?.icon} {t(c?.labelKey || ty)}
              </button>
            );
          })}
        </div>
      )}
      {renderPanel(getEditorType(activeType))}
    </div>
  );
};

const NumberField: React.FC<{ label: string; value: number; step?: number; min?: number; onChange: (v: string) => void }> = ({
  label, value, step = 0.1, min, onChange,
}) => (
  <div>
    <label className="text-[10px] font-medium text-salvi-grey">{label}</label>
    <input
      type="number" step={step} min={min} value={value}
      onChange={e => onChange(e.target.value)}
      className="mt-1 w-full rounded border border-salvi-line bg-white px-2 py-1.5 text-xs"
    />
  </div>
);

export default EditorInspector;
