/** Shared geometry-info block for a road segment (used by popup and hover). */
import React from 'react';
import type { GisPlanningInventoryTarget } from '../../types';

const SRC_ICON: Record<string, string> = {
  osm_width: '📏', lanes: '🔢', default: '⚠', ign_rt: '🛰', mapillary: '📷',
  catastro: '🏛', survey: '✅', osm_buildings: '🏠', overture: '🌐', satellite: '🛰️',
};
const SRC_LABEL: Record<string, string> = {
  osm_width: 'OSM directo', lanes: 'carriles×3.0', default: 'estimado por tipo',
  ign_rt: 'IGN IGR-RT', mapillary: 'Mapillary', catastro: 'Catastro', survey: 'campo',
  osm_buildings: 'OSM edificios', overture: 'Overture Maps', satellite: 'Satélite (preciso)',
};

export const SegmentGeometryInfo: React.FC<{
  target: GisPlanningInventoryTarget;
  compact?: boolean;
}> = ({ target, compact }) => {
  const segWidth = target.estWidth ?? null;
  const swL = target.sidewalkWidthLeft ?? ((target.sidewalk === 'both' || target.sidewalk === 'left') ? 2.0 : null);
  const swR = target.sidewalkWidthRight ?? ((target.sidewalk === 'both' || target.sidewalk === 'right') ? 2.0 : null);
  const hasSidewalk = swL != null || swR != null || target.sidewalk != null;
  const widthIsEst = target.widthSrc && !['osm_width', 'ign_rt', 'mapillary', 'overture', 'satellite'].includes(target.widthSrc);
  const src = (target.widthSrc && SRC_ICON[target.widthSrc]) || '❓';
  const srcLbl = (target.widthSrc && SRC_LABEL[target.widthSrc]) || 'desconocido';
  const srcByAttr = target.geomSources || {};

  return (
    <div className={compact ? 'text-[10px] text-salvi-muted' : 'border-b border-salvi-line/50 px-3 py-2 text-[10px] text-salvi-muted'}>
      {/* Tramo index within street */}
      {target.tramoOf != null && target.tramoOf > 1 && (
        <div className="flex flex-wrap gap-x-3 gap-y-0.5">
          <span className="rounded bg-salvi-surface px-1 font-medium text-salvi-grey">
            Tramo {target.tramoSeq ?? 1}/{target.tramoOf}
          </span>
        </div>
      )}

      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
        {segWidth != null && (
          <span title={`Fuente: ${srcLbl}`}>
            {src} Calzada {segWidth} m
            <span className="opacity-50"> · {srcLbl}</span>
          </span>
        )}
        {target.platformWidth != null && target.platformWidth !== segWidth && (
          <span title={target.geomSources?.platformWidth === 'catastro' ? 'Ancho de sección (fachada a fachada) — Catastro' : 'Ancho de sección (fachada a fachada) — edificios OSM'}>
            🏠 Sección {target.platformWidth} m
          </span>
        )}
        {target.lanes != null && (
          <span title={target.geomSources?.lanes === 'ign_rt' ? 'Carriles según IGN IGR-RT' : 'Carriles según OSM'}>
            🚗 {target.lanes} carriles
            {target.geomSources?.lanes === 'ign_rt' && <span className="ml-0.5 rounded bg-salvi-surface px-1 text-[8px] text-salvi-grey">IGN</span>}
          </span>
        )}
      </div>

      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
        {swL != null && (
          <span title={target.sidewalkWidthLeft != null ? 'OSM sidewalk:width' : 'Estimado 2.0m'}>
            🚶 Acera I {swL} m{target.sidewalkWidthLeft != null ? ' (OSM)' : ' (est.)'}
          </span>
        )}
        {swR != null && (
          <span title={target.sidewalkWidthRight != null ? 'OSM sidewalk:width' : 'Estimado 2.0m'}>
            🚶 Acera D {swR} m{target.sidewalkWidthRight != null ? ' (OSM)' : ' (est.)'}
          </span>
        )}
        {!swL && !swR && target.sidewalk && (
          <span>🚶 sidewalk: {target.sidewalk} <span className="opacity-50">(sin dimensión)</span></span>
        )}
        {!hasSidewalk && <span className="opacity-50">🚶 Sin datos de acera</span>}
      </div>

      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
        {target.dual && <span className="text-state-info">🛤 Doble calzada{target.median ? ' con mediana' : ''}</span>}
        {target.median && target.medianWidth != null && <span className="text-state-info">📐 Mediana {target.medianWidth} m</span>}
        {target.cyclewayWidth != null && <span>🚲 Carril bici {target.cyclewayWidth} m</span>}
        {target.maxspeed != null && <span>⏱ {target.maxspeed} km/h</span>}
        {target.parking && <span>🅿️ {target.parking}</span>}
        {target.shoulderWidth != null && <span>↔️ Arcén {target.shoulderWidth} m</span>}
        {target.functionalClass && <span className="opacity-70">📋 {target.functionalClass}</span>}
      </div>

      {widthIsEst && <div className="mt-0.5 text-[9px] text-state-warning">⚠ Calzada estimada — verificar in situ</div>}
      {!widthIsEst && target.widthSrc === 'satellite' && <div className="mt-0.5 text-[9px] text-state-success">✓ Calzada medida por satélite</div>}

      {/* Provenance: which source provided each measured attribute */}
      {Object.keys(srcByAttr).length > 0 && !compact && (
        <div className="mt-1 text-[9px] opacity-60">
          Fuentes: {Object.entries(srcByAttr).map(([k, v]) => `${k}=${v}`).join(', ')}
        </div>
      )}
    </div>
  );
};

export default SegmentGeometryInfo;
