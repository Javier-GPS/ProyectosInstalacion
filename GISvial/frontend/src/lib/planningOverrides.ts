import type { GisPlanningInventory, GisPlanningInventoryTarget, GisPlanningPatch, GisPlanningPayload } from '../types';

export const ROAD_CHAR_KEYS = [
  'estWidth', 'lanes', 'lanesForward', 'lanesBackward',
  'sidewalk', 'sidewalkWidthLeft', 'sidewalkWidthRight',
  'median', 'medianWidth', 'dual', 'maxspeed',
] as const;

export type RoadCharKey = (typeof ROAD_CHAR_KEYS)[number];

export const effectivePatch = (payload: GisPlanningPayload, target: GisPlanningInventoryTarget): GisPlanningPatch =>
  ({ ...(payload.group_defaults[target.group_ref] || {}), ...(payload.target_overrides[target.target_ref] || {}) });

export const applyRoadOverrides = (target: GisPlanningInventoryTarget, patch: GisPlanningPatch): GisPlanningInventoryTarget => {
  const out = { ...target };
  for (const key of ROAD_CHAR_KEYS) {
    if (patch[key] !== undefined) (out as any)[key] = patch[key];
  }
  return out;
};

export const hasRoadOverrides = (patch: GisPlanningPatch): boolean =>
  ROAD_CHAR_KEYS.some(key => patch[key] !== undefined);

/** Inventory with road-characteristic overrides applied to each target. */
export const effectiveInventory = (inventory: GisPlanningInventory, payload: GisPlanningPayload): GisPlanningInventory => {
  const targets = inventory.targets.map(target => {
    const patch = effectivePatch(payload, target);
    return hasRoadOverrides(patch) ? applyRoadOverrides(target, patch) : target;
  });
  return { ...inventory, targets };
};
