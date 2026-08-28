import React, { useMemo, useState } from 'react';
import { useI18n } from '../../i18n';
import { useGisStore, ROAD_CFG, type DetailSelectionMode } from '../../store/useGisStore';
import { exportDxf } from '../../lib/api';
import { useApi } from '../../hooks/useApi';
import { targetDisplayLabel, targetSelectionKey } from '../../lib/roadNaming';

const StepLuminarias: React.FC = () => {
  const { t } = useI18n();
  const selectedZoneId = useGisStore(s => s.selectedZoneId);
  const inventory = useGisStore(s => s.activePlanningInventory);
  const planningPayload = useGisStore(s => s.planningPayload);
  const zoneLuminaires = useGisStore(s => s.zoneLuminaires);
  const selectedLumIds = useGisStore(s => s.selectedLumIds);
  const accumulatedSelection = useGisStore(s => s.accumulatedSelection);
  const toggleTargetSelection = useGisStore(s => s.toggleTargetSelection);
  const detailSelectionMode = useGisStore(s => s.detailSelectionMode);
  const setDetailSelectionMode = useGisStore(s => s.setDetailSelectionMode);
  const clearSelection = useGisStore(s => s.clearSelection);
  const showCompliance = useGisStore(s => s.showCompliance);
  const setShowCompliance = useGisStore(s => s.setShowCompliance);
  const setStepWizard = useGisStore(s => s.setStepWizard);
  const { call: callExport } = useApi<Blob>();

  const zoneId = selectedZoneId;
  const lums = zoneId ? (zoneLuminaires[zoneId] || []) : [];
  const selectedCount = selectedLumIds.size;

  const zoneSelection = zoneId ? (accumulatedSelection[zoneId] || {}) : {};
  const selEntries = Object.keys(zoneSelection);

  const [selExpandedStreet, setSelExpandedStreet] = useState<string | null>(null);

  // Group selected targets by street name
  const streets = useMemo(() => {
    if (!inventory || !selEntries.length) return [];
    const byStreet: Record<string, { label: string; targets: typeof inventory.targets; selected: typeof inventory.targets; roadType: string | null }> = {};
    for (const t of inventory.targets) {
      const key = targetSelectionKey(t);
      if (!byStreet[key]) {
        const grp = inventory.groups.find(g => g.group_ref === t.group_ref);
        byStreet[key] = { label: targetDisplayLabel(t), targets: [], selected: [], roadType: grp?.road_type || null };
      }
      byStreet[key].targets.push(t);
      if (zoneSelection[t.target_ref]) byStreet[key].selected.push(t);
    }
    return Object.entries(byStreet).filter(([, v]) => v.selected.length).map(([key, v]) => ({ key, street: v.label, ...v }));
  }, [inventory, zoneSelection, selEntries.length]);

  const handleExportDxf = async () => {
    if (!zoneId) return;
    try {
      const blob = await callExport((signal) => exportDxf(zoneId, signal));
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `zone_${zoneId}.dxf`;
      a.click(); URL.revokeObjectURL(url);
    } catch (err) { console.error(err); }
  };

  return (
    <div className="gis-panel rounded-xl overflow-hidden flex flex-col max-h-full">
      <div className="p-3 border-b border-salvi-line">
        <h2 className="text-sm font-semibold text-salvi-black">{t('detail.elements', { n: lums.length })}</h2>
      </div>

      {/* Selected streets / segments */}
      {streets.length > 0 && (
        <div className="border-b border-salvi-line/50 max-h-32 overflow-y-auto gis-scroll bg-salvi-surface/30">
          <div className="px-3 py-1.5 text-[9px] font-semibold uppercase tracking-wide text-salvi-muted">Tramos seleccionados</div>
          {streets.map(({ key, street, targets, selected, roadType }) => {
            const selectableTargets = targets.filter(target => target.geometry);
            const all = selectableTargets.length > 0 && selected.filter(target => target.geometry).length === selectableTargets.length;
            const open = selExpandedStreet === key;
            const scfg = roadType ? ROAD_CFG[roadType] : undefined;
            return (
              <div key={key}>
                <div className="flex items-center gap-1.5 border-b border-salvi-line/20 px-3 py-1.5 last:border-0">
                  <button onClick={() => setSelExpandedStreet(open ? null : key)} className="shrink-0 text-[8px] text-salvi-muted transition-transform hover:text-salvi-black">
                    ▶
                  </button>
                  <input type="checkbox" checked={all} ref={el => { if (el) el.indeterminate = !all && selected.length > 0; }}
                    disabled={!selectableTargets.length}
                    onChange={() => { if (zoneId) { const refs = selectableTargets.map(t => t.target_ref); if (all) refs.forEach(r => toggleTargetSelection(zoneId, r)); else refs.forEach(r => { if (!zoneSelection[r]) toggleTargetSelection(zoneId, r); }); } }}
                    className="shrink-0 cursor-pointer"
                  />
                  <span className="flex-1 truncate text-[10px] font-medium text-salvi-black">{street}</span>
                  <span className="text-[9px] text-salvi-muted">{selected.length}/{targets.length}</span>
                </div>
                {open && (() => {
                  const groups: { w: number | null; segs: typeof selected }[] = [];
                  for (const t of selected) {
                    const w = t.estWidth ?? scfg?.width ?? null;
                    const last = groups[groups.length - 1];
                    if (last && last.w === w) last.segs.push(t);
                    else groups.push({ w, segs: [t] });
                  }
                  return (
                    <div className="border-b border-salvi-line/10 bg-salvi-surface/20">
                      {groups.map((g, gi) => {
                        const t = g.segs[0];
                        const sw = t.sidewalk;
                        const sl = t.sidewalkWidthLeft ?? (sw === 'both' || sw === 'left' ? 2.0 : null);
                        const sr = t.sidewalkWidthRight ?? (sw === 'both' || sw === 'right' ? 2.0 : null);
                        const est = t.widthSrc !== 'osm_width' ? '⚠' : '';
                        const totalM = g.segs.reduce((s, x) => s + (x.length_m || 0), 0);
                        return (
                          <div key={gi} className="flex items-center gap-2 px-5 py-1 text-[9px] text-salvi-muted">
                            <span className="w-16 shrink-0">{g.segs.length} tramos</span>
                            <span className="w-14 shrink-0">{Math.round(totalM)}m</span>
                            {g.w != null && <span className="w-14 shrink-0">{est}C {g.w}m</span>}
                            {sl != null && <span className="w-14 shrink-0">AI {sl}m</span>}
                            {sr != null && <span className="w-14 shrink-0">AD {sr}m</span>}
                          </div>
                        );
                      })}
                    </div>
                  );
                })()}
              </div>
            );
          })}
        </div>
      )}

      {/* Selection modes */}
      <div className="p-2 border-b border-salvi-line flex gap-1 flex-wrap">
        {(['none', 'click', 'marquee', 'lasso', 'criteria'] as DetailSelectionMode[]).map(mode => (
          <button
            key={mode}
            onClick={() => setDetailSelectionMode(mode)}
            className={`text-xs px-2 py-1 rounded-md transition-colors ${
              detailSelectionMode === mode
                ? 'bg-salvi-black text-white'
                : 'bg-salvi-surface text-salvi-grey hover:bg-salvi-line'
            }`}
          >
            {t(`detail.select.${mode}`)}
          </button>
        ))}
      </div>

      {/* Lumi list */}
      <div className="overflow-y-auto flex-1 gis-scroll">
        {lums.map(lum => {
          const isSelected = selectedLumIds.has(`${zoneId}__${lum.id}`);
          return (
            <div
              key={lum.id}
              className={`px-3 py-2 border-b border-salvi-line/30 text-xs cursor-pointer transition-colors ${
                isSelected ? 'bg-yellow-50 border-l-2 border-l-yellow-400' : 'hover:bg-salvi-surface'
              }`}
            >
              <div className="font-medium text-salvi-black">{lum.street_name || '—'}</div>
              <div className="text-salvi-muted">{lum.road_type} · {lum.watts}W · {lum.lighting_class}</div>
            </div>
          );
        })}
        {!lums.length && (
          <div className="p-6 text-center text-xs text-salvi-muted">No hay luminarias</div>
        )}
      </div>

      {/* Bottom actions */}
      <div className="p-3 border-t border-salvi-line space-y-2">
        {selectedCount > 0 && (
          <div className="flex items-center justify-between">
            <span className="text-xs text-salvi-muted">{selectedCount} seleccionadas</span>
            <button onClick={clearSelection} className="text-xs text-state-danger">{t('actions.cancel')}</button>
          </div>
        )}

        <div className="flex gap-2">
          <button
            onClick={() => setShowCompliance(!showCompliance)}
            className={`flex-1 text-xs rounded-md py-1.5 border transition-colors ${
              showCompliance
                ? 'bg-state-success/10 border-state-success text-state-success'
                : 'border-salvi-line text-salvi-grey hover:bg-salvi-surface'
            }`}
          >
            {showCompliance ? t('detail.compliance.hide') : t('detail.compliance.show')}
          </button>
          <button
            onClick={handleExportDxf}
            className="flex-1 text-xs border border-salvi-line rounded-md py-1.5 text-salvi-black hover:bg-salvi-surface"
          >
            {t('export.dxf')}
          </button>
        </div>

        <div className="flex justify-between pt-1">
          <button onClick={() => setStepWizard('vias')} className="text-xs text-salvi-grey">{'< '} Vías</button>
          <button onClick={() => setStepWizard('informe')} className="text-xs bg-salvi-black text-white rounded-md px-3 py-1">
            {t('detail.lux.export')} {'>'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default StepLuminarias;
