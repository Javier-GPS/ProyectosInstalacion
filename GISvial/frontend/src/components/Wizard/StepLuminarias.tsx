import React from 'react';
import { useI18n } from '../../i18n';
import { useGisStore, type DetailSelectionMode } from '../../store/useGisStore';
import { exportDxf } from '../../lib/api';
import { useApi } from '../../hooks/useApi';

const StepLuminarias: React.FC = () => {
  const { t } = useI18n();
  const selectedZoneId = useGisStore(s => s.selectedZoneId);
  const zoneLuminaires = useGisStore(s => s.zoneLuminaires);
  const selectedLumIds = useGisStore(s => s.selectedLumIds);
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
