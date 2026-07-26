import React from 'react';
import { useI18n } from '../../i18n';
import { useGisStore, type DetailSelectionMode } from '../../store/useGisStore';
import { exportDxf } from '../../lib/api';

interface DetailPanelProps {
  side: 'left' | 'right';
}

const DetailPanel: React.FC<DetailPanelProps> = ({ side }) => {
  const { t } = useI18n();
  const detailZoneId = useGisStore(s => s.detailZoneId);
  const zoneLuminaires = useGisStore(s => s.zoneLuminaires);
  const selectedLumIds = useGisStore(s => s.selectedLumIds);
  const detailSelectionMode = useGisStore(s => s.detailSelectionMode);
  const setDetailSelectionMode = useGisStore(s => s.setDetailSelectionMode);
  const clearSelection = useGisStore(s => s.clearSelection);
  const showCompliance = useGisStore(s => s.showCompliance);
  const setShowCompliance = useGisStore(s => s.setShowCompliance);

  const lums = detailZoneId ? (zoneLuminaires[detailZoneId] || []) : [];
  const selectedCount = selectedLumIds.size;

  if (side === 'left') {
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

        {/* Luminaire list */}
        <div className="overflow-y-auto flex-1 gis-scroll">
          {lums.map(lum => {
            const isSelected = selectedLumIds.has(`${detailZoneId}__${lum.id}`);
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
      </div>
    );
  }

  // Right panel — Inspector + Actions
  return (
    <div className="gis-panel rounded-xl overflow-hidden flex flex-col max-h-full">
      <div className="p-3 border-b border-salvi-line">
        <h2 className="text-sm font-semibold text-salvi-black">{t('detail.inspector')}</h2>
        {selectedCount > 0 && (
          <span className="text-xs text-salvi-muted">{selectedCount} seleccionadas</span>
        )}
      </div>

      <div className="overflow-y-auto flex-1 gis-scroll p-3 space-y-4">
        {/* Selection info */}
        {selectedCount > 0 && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-salvi-grey">{t('detail.batch.apply')}</span>
              <button onClick={clearSelection} className="text-xs text-state-danger">{t('actions.cancel')}</button>
            </div>
            <div className="space-y-1.5">
              <DetailField label={t('detail.edit.power')} value="150" />
              <DetailField label={t('detail.edit.height')} value="9" />
              <DetailField label={t('detail.edit.tilt')} value="5" />
              <DetailField label={t('detail.edit.arm')} value="1.5" />
              <DetailField label={t('detail.edit.spacing')} value="30" />
            </div>
            <button className="w-full text-xs bg-salvi-black text-white rounded-md py-1.5">
              {t('detail.batch.apply')}
            </button>
          </div>
        )}

        {/* Lux Studio actions */}
        <div>
          <span className="text-xs font-semibold text-salvi-grey uppercase tracking-wider block mb-2">
            Lux Studio
          </span>
          <div className="space-y-1.5">
            <button className="w-full text-xs border border-salvi-line rounded-md py-1.5 text-salvi-black hover:bg-salvi-surface">
              {t('detail.lux.export')}
            </button>
            <button className="w-full text-xs border border-salvi-line rounded-md py-1.5 text-salvi-black hover:bg-salvi-surface">
              {t('detail.lux.import')}
            </button>
          </div>
        </div>

        {/* Compliance */}
        <div>
          <button
            onClick={() => setShowCompliance(!showCompliance)}
            className={`w-full text-xs rounded-md py-1.5 border transition-colors ${
              showCompliance
                ? 'bg-state-success/10 border-state-success text-state-success'
                : 'border-salvi-line text-salvi-grey hover:bg-salvi-surface'
            }`}
          >
            {showCompliance ? t('detail.compliance.hide') : t('detail.compliance.show')}
          </button>
        </div>

        {/* Exports */}
        <div>
          <span className="text-xs font-semibold text-salvi-grey uppercase tracking-wider block mb-2">
            {t('export.dxf')}
          </span>
          <div className="space-y-1.5">
            <button
              onClick={async () => {
                if (!detailZoneId) return;
                try {
                  const blob = await exportDxf(detailZoneId);
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url; a.download = `zone_${detailZoneId}.dxf`;
                  a.click(); URL.revokeObjectURL(url);
                } catch (err) { console.error(err); }
              }}
              className="w-full text-xs border border-salvi-line rounded-md py-1.5 text-salvi-black hover:bg-salvi-surface"
            >
              {t('export.dxf')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

const DetailField: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="flex items-center gap-2">
    <label className="text-xs text-salvi-grey flex-1">{label}</label>
    <input
      type="text"
      defaultValue={value}
      className="w-20 border border-salvi-line rounded-md px-2 py-1 text-xs text-right"
    />
  </div>
);

export default DetailPanel;
