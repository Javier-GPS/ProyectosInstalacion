import React from 'react';
import { useI18n } from '../../i18n';
import { useGisStore } from '../../store/useGisStore';
import { EDITOR_OBJECT_TYPES } from '../../lib/editorObjects';

interface Props {
  view3d: boolean;
  base: 'plan' | 'aerial';
  layers: Record<string, boolean>;
  onToggleView: () => void;
  onToggleBase: () => void;
  onReset: () => void;
  onToggleLayer: (key: string) => void;
  onSave: () => void;
  onExport: () => void;
}

const EditorToolbar: React.FC<Props> = ({ view3d, base, layers, onToggleView, onToggleBase, onReset, onToggleLayer, onSave, onExport }) => {
  const { t } = useI18n();
  const editorTool = useGisStore(s => s.editorTool);
  const setEditorTool = useGisStore(s => s.setEditorTool);
  const editorZoneId = useGisStore(s => s.editorZoneId);
  const editorSaved = useGisStore(s => s.editorSaved);
  const editorObjects = useGisStore(s => s.editorObjects);
  const editorPlaceOffset = useGisStore(s => s.editorPlaceOffset);
  const setEditorPlaceOffset = useGisStore(s => s.setEditorPlaceOffset);
  const closeEditor = useGisStore(s => s.closeEditor);

  const isPlaceTool = editorTool != null && EDITOR_OBJECT_TYPES.some(t => t.key === editorTool);

  const count = editorZoneId ? (editorObjects[editorZoneId] || []).length : 0;
  const saved = editorZoneId ? editorSaved[editorZoneId] !== false : true;

  const layerKeys: { key: string; labelKey: string }[] = [
    { key: 'buildings', labelKey: 'editor.buildings' },
    { key: 'trees', labelKey: 'editor.trees' },
    { key: 'luminaries', labelKey: 'editor.luminaries' },
    { key: 'roads', labelKey: 'editor.roads' },
    { key: 'sidewalks', labelKey: 'editor.sidewalks' },
    { key: 'objects', labelKey: 'editor.objects' },
  ];

  return (
    <div className="flex h-full w-60 flex-col border-r border-salvi-line bg-white">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-salvi-line px-3 py-2">
        <span className="text-sm font-semibold text-salvi-black">🏙 {t('editor.title')}</span>
        <button onClick={() => { if (!saved && !window.confirm(t('editor.confirmClose'))) return; closeEditor(); }}
          className="rounded px-2 py-1 text-xs text-salvi-grey hover:bg-salvi-surface">{t('editor.close')}</button>
      </div>

      <div className="gis-scroll flex-1 space-y-4 overflow-y-auto p-3">
        {/* Tools */}
        <section>
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-salvi-muted">{t('editor.tools')}</div>
          <div className="grid grid-cols-3 gap-1.5">
            <button
              onClick={() => setEditorTool(null)}
              className={`flex flex-col items-center gap-0.5 rounded border px-1 py-2 text-[10px] ${
                editorTool === null ? 'border-salvi-black bg-salvi-black/5 text-salvi-black' : 'border-salvi-line text-salvi-grey hover:bg-salvi-surface'
              }`}
              title={t('editor.selectTool')}
            >
              <span className="text-base">✋</span>{t('editor.selectTool')}
            </button>
            <button
              onClick={() => setEditorTool('lasso')}
              className={`flex flex-col items-center gap-0.5 rounded border px-1 py-2 text-[10px] ${
                editorTool === 'lasso' ? 'border-salvi-black bg-salvi-black/5 text-salvi-black' : 'border-salvi-line text-salvi-grey hover:bg-salvi-surface'
              }`}
              title={t('editor.lasso')}
            >
              <span className="text-base">✨</span>{t('editor.lasso')}
            </button>
            <button
              onClick={() => setEditorTool('farolas_route')}
              className={`flex flex-col items-center gap-0.5 rounded border px-1 py-2 text-[10px] ${
                editorTool === 'farolas_route' ? 'border-salvi-black bg-salvi-black/5 text-salvi-black' : 'border-salvi-line text-salvi-grey hover:bg-salvi-surface'
              }`}
              title={t('editor.farolaRoute')}
            >
              <span className="text-base">⚡</span>{t('editor.farolaRoute')}
            </button>
            <button
              onClick={() => setEditorTool('medir')}
              className={`flex flex-col items-center gap-0.5 rounded border px-1 py-2 text-[10px] ${
                editorTool === 'medir' ? 'border-salvi-black bg-salvi-black/5 text-salvi-black' : 'border-salvi-line text-salvi-grey hover:bg-salvi-surface'
              }`}
              title={t('editor.measure')}
            >
              <span className="text-base">📏</span>{t('editor.measure')}
            </button>
            {EDITOR_OBJECT_TYPES.map(type => (
              <button
                key={type.key}
                onClick={() => setEditorTool(type.key)}
                className={`flex flex-col items-center gap-0.5 rounded border px-1 py-2 text-[10px] ${
                  editorTool === type.key ? 'border-salvi-black bg-salvi-black/5 text-salvi-black' : 'border-salvi-line text-salvi-grey hover:bg-salvi-surface'
                }`}
                title={t(type.labelKey)}
              >
                <span className="text-base">{type.icon}</span>{t(type.labelKey)}
              </button>
            ))}
          </div>
          {editorTool && (
            <p className="mt-1.5 text-[10px] text-salvi-muted">
              {editorTool === 'farolas_route' ? t('editor.farolaRouteHint') : editorTool === 'medir' ? t('editor.measureHint') : t('editor.placeHint')}
            </p>
          )}
          {isPlaceTool && (
            <div className="mt-1.5">
              <label className="text-[10px] font-medium text-salvi-grey">{t('editor.offsetFromRoad')}</label>
              <input
                type="number" min={0} step={0.5} value={editorPlaceOffset}
                onChange={e => setEditorPlaceOffset(parseFloat(e.target.value) || 0)}
                className="mt-0.5 w-full rounded border border-salvi-line bg-white px-2 py-1 text-[11px]"
              />
              <p className="mt-1 text-[9px] text-salvi-muted">{t('editor.offsetHint')}</p>
            </div>
          )}
        </section>

        {/* View */}
        <section>
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-salvi-muted">{t('editor.view')}</div>
          <div className="flex gap-1.5">
            <button onClick={onToggleView}
              className="flex-1 rounded border border-salvi-line px-2 py-1.5 text-xs hover:bg-salvi-surface">
              {view3d ? t('editor.view2d') : t('editor.view3d')}
            </button>
            <button onClick={onReset}
              className="flex-1 rounded border border-salvi-line px-2 py-1.5 text-xs hover:bg-salvi-surface">
              {t('editor.reset')}
            </button>
          </div>
          <button onClick={onToggleBase}
            className="mt-1.5 w-full rounded border border-salvi-line px-2 py-1.5 text-xs hover:bg-salvi-surface">
            {base === 'plan' ? '🛰 ' + t('editor.satellite') : '🗺 ' + t('editor.map')}
          </button>
        </section>

        {/* Layers */}
        <section>
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-salvi-muted">{t('editor.layers')}</div>
          <div className="space-y-1">
            {layerKeys.map(l => (
              <label key={l.key} className="flex items-center gap-2 text-xs text-salvi-grey">
                <input type="checkbox" checked={!!layers[l.key]} onChange={() => onToggleLayer(l.key)} className="cursor-pointer" />
                {t(l.labelKey)}
              </label>
            ))}
          </div>
        </section>
      </div>

      {/* Footer */}
      <div className="border-t border-salvi-line p-3">
        <button
          onClick={onExport}
          className="mb-2 w-full rounded border border-salvi-line px-3 py-2 text-xs font-medium text-salvi-black hover:bg-salvi-surface"
        >
          {t('export.dxf')}
        </button>
        <button
          onClick={onSave}
          className="w-full rounded bg-salvi-black px-3 py-2 text-xs font-semibold text-white hover:opacity-90"
        >
          {saved ? `✓ ${t('editor.saved')}` : t('editor.save')}
        </button>
        <p className="mt-1 text-center text-[10px] text-salvi-muted">
          {t('editor.objects')}: {count}
        </p>
      </div>
    </div>
  );
};

export default EditorToolbar;
