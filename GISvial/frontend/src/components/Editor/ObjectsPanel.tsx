/** Panel de objetos añadidos al editor: lista, selección inequívoca y borrado.
 *  Al seleccionar un objeto se muestra su editor (EditorInspector) debajo. */
import React from 'react';
import { useI18n } from '../../i18n';
import { useGisStore } from '../../store/useGisStore';
import { getEditorType } from '../../lib/editorObjects';
import EditorInspector from './EditorInspector';

const ObjectsPanel: React.FC = () => {
  const { t } = useI18n();
  const zoneId = useGisStore(s => s.editorZoneId);
  const objects = useGisStore(s => (s.editorZoneId ? s.editorObjects[s.editorZoneId] : undefined)) || [];
  const selectedIds = useGisStore(s => s.editorSelectedIds);
  const selectEditorObjects = useGisStore(s => s.selectEditorObjects);
  const removeEditorObjects = useGisStore(s => s.removeEditorObjects);

  const selectedObjects = selectedIds.length ? objects.filter(o => selectedIds.includes(o.id)) : [];

  const close = () => { selectEditorObjects([]); useGisStore.getState().setEditorRoadRef(null); };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-salvi-line px-3 py-2">
        <span className="text-sm font-semibold text-salvi-black">🧩 {t('editor.objects')}</span>
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-salvi-surface px-1.5 text-[10px] text-salvi-muted">{objects.length}</span>
          <button onClick={close} title="Cerrar" className="rounded p-1 text-[11px] text-salvi-muted hover:bg-salvi-surface hover:text-salvi-grey">
            ✕
          </button>
        </div>
      </div>

      <div className="gis-scroll max-h-[38%] overflow-y-auto p-2">
        {!objects.length ? (
          <p className="px-1 py-2 text-center text-[10px] text-salvi-muted">Sin objetos añadidos</p>
        ) : (
          <div className="space-y-1">
            {objects.map((o, i) => {
              const def = getEditorType(o.type);
              const label = o.label || t(def?.labelKey || o.type);
              const isSel = selectedIds.includes(o.id);
              return (
                <div
                  key={o.id}
                  onClick={() => { selectEditorObjects([o.id]); useGisStore.getState().setEditorRoadRef(null); }}
                  className={`group flex cursor-pointer items-center gap-1.5 rounded border px-1.5 py-1 text-[11px] ${
                    isSel ? 'border-salvi-black bg-salvi-black/5 text-salvi-black' : 'border-salvi-line text-salvi-grey hover:bg-salvi-surface'
                  }`}
                >
                  <span className="text-sm">{def?.icon || '❓'}</span>
                  <span className="flex-1 truncate">
                    <span className="font-medium">{label}</span>
                    <span className="ml-1 text-[9px] opacity-60">#{i + 1}</span>
                  </span>
                  <button
                    onClick={e => { e.stopPropagation(); zoneId && removeEditorObjects(zoneId, [o.id]); }}
                    title="Eliminar"
                    className="rounded px-1 text-[10px] text-salvi-muted opacity-0 transition-opacity group-hover:opacity-100 hover:text-[#B42318]"
                  >
                    🗑
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {selectedObjects.length > 0 && (
        <div className="flex-1 overflow-hidden border-t border-salvi-line">
          <EditorInspector objects={selectedObjects} />
        </div>
      )}
    </div>
  );
};

export default ObjectsPanel;
