import type { GisPlanningInventoryTarget } from '../types';

export const targetName = (target: GisPlanningInventoryTarget) => target.osmName ?? target.name ?? null;
export const targetRef = (target: GisPlanningInventoryTarget) => target.osmRef ?? target.ref ?? null;

export const targetDisplayLabel = (target: GisPlanningInventoryTarget) => {
  const name = targetName(target);
  if (name) return name;
  const ref = targetRef(target);
  if (ref) return `Ref. ${ref}`;
  return `Tramo OSM ${target.source_index + 1}`;
};

export const targetGroupKey = (target: GisPlanningInventoryTarget) => {
  const name = targetName(target);
  if (name) return `name:${name}`;
  const ref = targetRef(target);
  if (ref) return `target:${target.target_ref}`;
  return `unnamed:${target.roadRole || 'other'}`;
};

export const targetGroupLabel = (target: GisPlanningInventoryTarget) => {
  const name = targetName(target);
  if (name) return name;
  const ref = targetRef(target);
  if (ref) return `Ref. ${ref}`;
  return 'Vías sin nombre OSM';
};

export const targetSelectionKey = (target: GisPlanningInventoryTarget) => {
  const name = targetName(target);
  if (name) return `name:${name}`;
  return `target:${target.target_ref}`;
};
