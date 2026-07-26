import React from 'react';
import { useI18n } from '../../i18n';
import { useGisStore, ROAD_CFG } from '../../store/useGisStore';
import { saveZoneConfig, saveZoneOsm } from '../../lib/api';
import type { GisZone, GisOsmData } from '../../types';

const PlanningPanel: React.FC = () => {
  const { t } = useI18n();
  const zones = useGisStore(s => s.zones);
  const selectedZoneId = useGisStore(s => s.selectedZoneId);
  const zoneOsm = useGisStore(s => s.zoneOsm);
  const zoneConfigs = useGisStore(s => s.zoneConfigs);
  const setZoneOsm = useGisStore(s => s.setZoneOsm);
  const setZoneConfig = useGisStore(s => s.setZoneConfig);

  const zone = zones.find(z => z.id === selectedZoneId) as GisZone | undefined;
  const osm = selectedZoneId ? zoneOsm[selectedZoneId] : undefined;
  const config = selectedZoneId ? zoneConfigs[selectedZoneId] : undefined;

  if (!zone) return null;

  /* ── OSM load (mock — real impl calls /api/zones/{id}/osm from backend) ── */
  const handleLoadOsm = async () => {
    if (!selectedZoneId) return;
    // The OSM data loads from the backend on zone select.
    // If not yet loaded, trigger reload
    try {
      const { getZoneOsm: loadOsm } = await import('../../lib/api');
      const data = await loadOsm(selectedZoneId);
      setZoneOsm(selectedZoneId, data);
    } catch (err) {
      console.error('Failed to load OSM', err);
    }
  };

  const handleSaveConfig = async () => {
    if (!selectedZoneId || !config) return;
    try {
      await saveZoneConfig(selectedZoneId, config);
    } catch (err) { console.error(err); }
  };

  const kmByType = osm?.km_by_type || {};
  const ways = osm?.ways || [];

  return (
    <div className="gis-panel rounded-xl overflow-hidden flex flex-col max-h-full">
      <div className="p-3 border-b border-salvi-line">
        <h2 className="text-sm font-semibold text-salvi-black truncate">{zone.name}</h2>
        <p className="text-xs text-salvi-muted">{zone.type} · {zone.id?.slice(0, 8)}</p>
      </div>

      <div className="overflow-y-auto flex-1 gis-scroll p-3 space-y-4">
        {/* OSM Stats */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-salvi-grey uppercase tracking-wider">OSM</span>
            <button
              onClick={handleLoadOsm}
              className="text-xs bg-salvi-grey/10 text-salvi-grey rounded-md px-2 py-0.5 hover:bg-salvi-grey/20"
            >
              {t('zone.osm.load')}
            </button>
          </div>
          {ways.length > 0 && (
            <div className="text-xs text-salvi-grey space-y-1">
              <div>{t('zone.osm.ways', { n: ways.length })}</div>
              {Object.entries(kmByType).map(([type, km]) => (
                <div key={type} className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full" style={{ backgroundColor: ROAD_CFG[type]?.color || '#999' }} />
                  <span>{t(ROAD_CFG[type]?.labelKey || type)}</span>
                  <span className="ml-auto font-medium">{t('zone.osm.km', { km: km.toFixed(1) })}</span>
                </div>
              ))}
            </div>
          )}
          {!ways.length && (
            <div className="text-xs text-salvi-muted italic">No hay datos OSM</div>
          )}
        </div>

        {/* Zone Configuration */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-salvi-grey uppercase tracking-wider">{t('zone.config.spacing')}</span>
            <button onClick={handleSaveConfig} className="text-xs bg-salvi-black text-white rounded-md px-2 py-0.5">
              {t('actions.save')}
            </button>
          </div>
          <div className="space-y-2">
            <ConfigField
              label={t('zone.config.spacing')}
              value={config?.spacing ?? zone.spacing ?? 30}
              onChange={v => selectedZoneId && setZoneConfig(selectedZoneId, { ...config, zone_id: selectedZoneId, spacing: v } as any)}
            />
          </div>
        </div>

        {/* Road type quick config */}
        <div>
          <span className="text-xs font-semibold text-salvi-grey uppercase tracking-wider mb-2 block">
            {t('detail.edit.class')}
          </span>
          <div className="space-y-1.5">
            {Object.entries(ROAD_CFG).map(([type, cfg]) => (
              <div key={type} className="flex items-center gap-2 text-xs text-salvi-grey">
                <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: cfg.color }} />
                <span className="w-20 truncate">{t(cfg.labelKey)}</span>
                <span className="text-salvi-muted">{cfg.defaultLightingClass}</span>
                <span className="ml-auto text-salvi-muted">{cfg.defaultSpacing}m</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

/* ── Simple config field ────────────────────────────────────────────────── */
const ConfigField: React.FC<{
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
}> = ({ label, value, onChange, min = 5, max = 100, step = 1 }) => (
  <div className="flex items-center gap-2">
    <label className="text-xs text-salvi-grey flex-1">{label}</label>
    <input
      type="number"
      value={value}
      onChange={e => onChange(parseFloat(e.target.value) || min)}
      min={min}
      max={max}
      step={step}
      className="w-20 border border-salvi-line rounded-md px-2 py-1 text-xs text-right"
    />
  </div>
);

export default PlanningPanel;
