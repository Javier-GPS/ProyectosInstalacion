export type PhotometricDisplayUnit = 'lux' | 'candela';
export type VisualizationScaleMode = 'auto' | 'manual';

export type VisualizationScale = {
  min: number;
  max: number;
};

export type BuildingPlacementConfig = {
  road_width: number;
  sidewalk_left: number;
  sidewalk_right: number;
  spacing: number;
  building_height: number;
  pole_count: number;
};

export const resolveVisualizationScale = (
  mode: VisualizationScaleMode,
  manualMin: number,
  manualMax: number,
  values: number[],
): VisualizationScale => {
  if (mode === 'manual') {
    const min = Number.isFinite(manualMin) ? manualMin : 0;
    const max = Number.isFinite(manualMax) ? manualMax : min + 1;
    return max > min ? { min, max } : { min, max: min + 1 };
  }

  const finite = values.filter(Number.isFinite);
  const max = Math.max(1, ...finite);
  const min = Math.min(0, ...finite);
  return { min, max };
};

export const normalizeByScale = (value: number, scale: VisualizationScale) => {
  const span = Math.max(1e-6, scale.max - scale.min);
  return Math.min(1, Math.max(0, (value - scale.min) / span));
};

export const powerVisualFactor = (power: number) => {
  const normalized = Math.sqrt(Math.max(1, power) / 100);
  return Math.min(1.8, Math.max(0.6, normalized));
};

export const unitSuffix = (unit: PhotometricDisplayUnit) => (unit === 'lux' ? 'lx' : 'cd/m²');

export const buildBuildingRows = (cfg: BuildingPlacementConfig, asObstacles: boolean = false) => {
  const length = Math.max(cfg.spacing * Math.max(1, cfg.pole_count - 1) * 1.3, 30);
  const depth = 4;
  const height = Math.max(1, cfg.building_height);
  const count = Math.max(3, Math.ceil(length / 8));
  const startX = -length / 2 + 3;
  const step = length / count;

  return Array.from({ length: count }, (_, index) => {
    const width = Math.max(3.5, step * 0.72);
    const x = startX + index * step + width / 2;
    return [
      { id: `left-${index}`, x, z: -cfg.sidewalk_left - depth / 2, width, depth, height, asObstacles },
      { id: `right-${index}`, x, z: cfg.road_width + cfg.sidewalk_right + depth / 2, width, depth, height, asObstacles },
    ];
  }).flat();
};
