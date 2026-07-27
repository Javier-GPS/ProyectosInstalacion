import React from 'react';
import { useI18n } from '../../i18n';
import { useGisStore } from '../../store/useGisStore';
import { exportDxf, exportPlantilla } from '../../lib/api';
import { useApi } from '../../hooks/useApi';
import { ROAD_CFG } from '../../store/types';

const StepInforme: React.FC = () => {
  const { t } = useI18n();
  const zones = useGisStore(s => s.zones);
  const planningInventory = useGisStore(s => s.activePlanningInventory);
  const zoneLuminaires = useGisStore(s => s.zoneLuminaires);
  const zonePhotometric = useGisStore(s => s.zonePhotometric);
  const selectedZoneId = useGisStore(s => s.selectedZoneId);
  const setStepWizard = useGisStore(s => s.setStepWizard);
  const { call: callExport } = useApi<any>();

  const zone = zones.find(z => z.id === selectedZoneId);
  const inventory = planningInventory?.zone_id === selectedZoneId ? planningInventory : undefined;
  const lums = selectedZoneId ? zoneLuminaires[selectedZoneId] || [] : [];
  const photometric = selectedZoneId ? zonePhotometric[selectedZoneId] || [] : [];

  const totalKm = inventory
    ? (inventory.groups.reduce((sum, group) => sum + group.length_m, 0) / 1000).toFixed(1)
    : '—';

  const compliancePass = photometric.filter(r => r.cumple?.toLowerCase() === 'si' || r.cumple === '1').length;
  const complianceFail = photometric.filter(r => r.cumple?.toLowerCase() === 'no' || r.cumple === '0').length;

  const handleExport = async (fmt: 'dxf' | 'plantilla') => {
    if (!selectedZoneId) return;
    try {
      if (fmt === 'dxf') {
        const blob = await callExport((signal) => exportDxf(selectedZoneId, signal));
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = `zone_${selectedZoneId}.dxf`;
        a.click(); URL.revokeObjectURL(url);
      } else {
        const rows = lums.map(l => ({
          wayKey: `${l.road_type}_${l.street_name}`,
          streetName: l.street_name,
          roadType: l.road_type,
          lightingClass: l.lighting_class,
          roadWidth: ROAD_CFG[l.road_type]?.width || 0,
          spacing: l.spacing,
          height: l.height_m || 0,
          armLen: l.arm_len || 0,
          tilt: l.tilt || 0,
          distribution: l.distribution || '',
          power: l.watts,
          lm: 0,
          model: '',
          lente: '',
        }));
        await callExport((signal) => exportPlantilla(selectedZoneId, rows, signal));
      }
    } catch (err) { console.error(err); }
  };

  if (!zone) {
    return (
      <div className="gis-panel rounded-xl p-6 text-center text-sm text-salvi-muted">
        Selecciona una zona para ver el informe
      </div>
    );
  }

  return (
    <div className="gis-panel rounded-xl overflow-hidden flex flex-col max-h-full">
      <div className="p-3 border-b border-salvi-line">
        <h2 className="text-sm font-semibold text-salvi-black">Informe: {zone.name}</h2>
      </div>

      <div className="overflow-y-auto flex-1 gis-scroll p-3 space-y-4">
        {/* KPIs */}
        <div className="grid grid-cols-2 gap-2">
          <div className="bg-salvi-surface rounded-lg p-3 text-center">
            <div className="text-2xl font-bold text-salvi-black">{totalKm}</div>
            <div className="text-xs text-salvi-muted">km de vías</div>
          </div>
          <div className="bg-salvi-surface rounded-lg p-3 text-center">
            <div className="text-2xl font-bold text-salvi-black">{lums.length}</div>
            <div className="text-xs text-salvi-muted">Luminarias</div>
          </div>
          <div className="bg-salvi-surface rounded-lg p-3 text-center">
            <div className="text-2xl font-bold text-state-success">{compliancePass}</div>
            <div className="text-xs text-salvi-muted">Cumplen</div>
          </div>
          <div className="bg-salvi-surface rounded-lg p-3 text-center">
            <div className="text-2xl font-bold text-state-danger">{complianceFail}</div>
            <div className="text-xs text-salvi-muted">No cumplen</div>
          </div>
        </div>

        {/* Ways summary */}
        {inventory && (
          <div>
            <span className="text-xs font-semibold text-salvi-grey uppercase tracking-wider block mb-2">Vías por tipo</span>
            <div className="space-y-1">
              {inventory.groups.map(group => (
                <div key={group.group_ref} className="flex items-center gap-2 text-xs text-salvi-grey">
                  <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: group.road_type ? ROAD_CFG[group.road_type]?.color || '#999' : '#999' }} />
                  <span>{group.road_type ? t(ROAD_CFG[group.road_type]?.labelKey || group.road_type) : 'Sin tipo'}</span>
                  <span className="ml-auto font-medium">{(group.length_m / 1000).toFixed(1)} km</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Export actions */}
        <div>
          <span className="text-xs font-semibold text-salvi-grey uppercase tracking-wider block mb-2">Exportar</span>
          <div className="space-y-1.5">
            <button
              onClick={() => handleExport('dxf')}
              className="w-full text-xs border border-salvi-line rounded-md py-1.5 text-salvi-black hover:bg-salvi-surface"
            >
              {t('export.dxf')}
            </button>
            <button
              onClick={() => handleExport('plantilla')}
              className="w-full text-xs border border-salvi-line rounded-md py-1.5 text-salvi-black hover:bg-salvi-surface"
            >
              {t('export.plantilla')}
            </button>
          </div>
        </div>
      </div>

      {/* Nav */}
      <div className="p-3 border-t border-salvi-line">
        <button onClick={() => setStepWizard('luminarias')} className="text-xs text-salvi-grey">{'< '} Luminarias</button>
      </div>
    </div>
  );
};

export default StepInforme;
