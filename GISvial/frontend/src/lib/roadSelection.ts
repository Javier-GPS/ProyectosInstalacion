import type maplibregl from 'maplibre-gl';
import type { GisPlanningInventory, GisPlanningInventoryTarget, GisZoneGeometry } from '../types';
import type { RoadSelectionAnchor, RoadSelectionDraft, RoadSelectionHit } from '../store/types';

const EARTH_M = 6371008.8;

export const roadSelectionIsCurrent = (draft: RoadSelectionDraft, inventory: GisPlanningInventory, boundary: GisZoneGeometry['boundary'] | undefined) =>
  draft.inventory_hash === inventory.base_inventory_hash
  && draft.boundary_signature === JSON.stringify(boundary)
  && [draft.a?.target_ref, draft.b?.target_ref].filter(Boolean).every(targetRef => inventory.targets.some(target => target.target_ref === targetRef));

export const distanceM = (a: [number, number], b: [number, number]) => {
  const lat1 = a[1] * Math.PI / 180;
  const lat2 = b[1] * Math.PI / 180;
  const dLat = lat2 - lat1;
  const dLon = (b[0] - a[0]) * Math.PI / 180;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return EARTH_M * 2 * Math.asin(Math.sqrt(h));
};

export const nearestLineHit = (
  map: maplibregl.Map,
  geometry: [number, number][],
  click: { x: number; y: number },
  tolerancePx = 12,
): RoadSelectionHit | null => {
  if (geometry.length < 2) return null;
  const point = click;
  const lengths = geometry.slice(0, -1).map((coordinate, index) => distanceM(coordinate, geometry[index + 1]));
  const total = lengths.reduce((sum, value) => sum + value, 0);
  if (!total) return null;
  let travelled = 0;
  let best: (RoadSelectionHit & { distance: number }) | null = null;
  for (let segmentIndex = 0; segmentIndex < geometry.length - 1; segmentIndex++) {
    const coordinate = geometry[segmentIndex];
    const first = map.project(coordinate);
    const second = map.project(geometry[segmentIndex + 1]);
    const dx = second.x - first.x;
    const dy = second.y - first.y;
    const denominator = dx * dx + dy * dy;
    const t = denominator ? Math.max(0, Math.min(1, ((point.x - first.x) * dx + (point.y - first.y) * dy) / denominator)) : 0;
    const x = first.x + t * dx;
    const y = first.y + t * dy;
    const distance = Math.hypot(point.x - x, point.y - y);
    if (!best || distance < best.distance) {
      best = {
        segment_index: segmentIndex,
        segment_t: t,
        measure: (travelled + t * lengths[segmentIndex]) / total,
        coordinate: [coordinate[0] + t * (geometry[segmentIndex + 1][0] - coordinate[0]), coordinate[1] + t * (geometry[segmentIndex + 1][1] - coordinate[1])],
        distance,
      };
    }
    travelled += lengths[segmentIndex];
  }
  if (!best || best.distance > tolerancePx) return null;
  const { distance: _distance, ...hit } = best;
  return hit;
};

export const nearestInventoryHit = (
  map: maplibregl.Map,
  targets: GisPlanningInventoryTarget[],
  click: { x: number; y: number },
  tolerancePx = 12,
): RoadSelectionAnchor | null => {
  console.log('[nearestInventoryHit] targets:', targets.length, 'click:', click, 'tolerance:', tolerancePx);
  let best: (RoadSelectionAnchor & { distance: number }) | null = null;
  for (const target of targets) {
    if (!target.geometry) continue;
    const hit = nearestLineHit(map, target.geometry, click, tolerancePx);
    if (!hit) continue;
    const projected = map.project(hit.coordinate);
    const distance = Math.hypot(projected.x - click.x, projected.y - click.y);
    console.log('[nearestInventoryHit] target:', target.target_ref, 'distance:', distance, 'hit:', hit);
    if (!best || distance < best.distance) best = { ...hit, target_ref: target.target_ref, distance };
  }
  if (!best) return null;
  const { distance: _distance, ...anchor } = best;
  return anchor;
};

const forwardSlice = (geometry: [number, number][], first: RoadSelectionHit, second: RoadSelectionHit) => {
  const path: [number, number][] = [first.coordinate];
  for (let index = first.segment_index + 1; index <= second.segment_index; index++) path.push(geometry[index]);
  if (path[path.length - 1][0] !== second.coordinate[0] || path[path.length - 1][1] !== second.coordinate[1]) path.push(second.coordinate);
  return path;
};

export const sliceLine = (geometry: [number, number][], a: RoadSelectionHit, b: RoadSelectionHit) => {
  if (Math.abs(a.measure - b.measure) < 1e-9) return null;
  const path = a.measure < b.measure ? forwardSlice(geometry, a, b) : forwardSlice(geometry, b, a).reverse();
  return { path, length_m: path.slice(0, -1).reduce((sum, point, index) => sum + distanceM(point, path[index + 1]), 0) };
};

const cross = (a: [number, number], b: [number, number]) => a[0] * b[1] - a[1] * b[0];

const pointOnSegment = (point: [number, number], a: [number, number], b: [number, number]) => {
  const ab: [number, number] = [b[0] - a[0], b[1] - a[1]];
  const ap: [number, number] = [point[0] - a[0], point[1] - a[1]];
  const length = Math.hypot(...ab);
  const projection = ap[0] * ab[0] + ap[1] * ab[1];
  return !!length && Math.abs(cross(ab, ap)) <= 1e-12 * length && projection >= -1e-12 * length && projection <= length ** 2 + 1e-12 * length;
};

const pointOnRing = (point: [number, number], ring: [number, number][]) =>
  ring.slice(0, -1).some((a, index) => pointOnSegment(point, a, ring[index + 1]));

const pointInRing = (point: [number, number], ring: [number, number][]) => {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if ((yi > point[1]) !== (yj > point[1]) && point[0] < (xj - xi) * (point[1] - yi) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
};

const pointInPolygon = (point: [number, number], polygon: [number, number][][]) =>
  !!polygon[0] && (pointOnRing(point, polygon[0]) || pointInRing(point, polygon[0]))
  && !polygon.slice(1).some(ring => !pointOnRing(point, ring) && pointInRing(point, ring));

export const pointInsideBoundary = (point: [number, number], boundary: NonNullable<GisZoneGeometry['boundary']>) => {
  const polygons = boundary.type === 'MultiPolygon' ? boundary.coordinates as [number, number][][][] : [boundary.coordinates as [number, number][][]];
  return polygons.some(polygon => pointInPolygon(point, polygon));
};

const ringIntersectionMeasures = (a: [number, number], b: [number, number], ring: [number, number][]) => {
  const r: [number, number] = [b[0] - a[0], b[1] - a[1]];
  const denominatorR = r[0] ** 2 + r[1] ** 2;
  const measures: number[] = [];
  ring.slice(0, -1).forEach((q, index) => {
    const next = ring[index + 1];
    const s: [number, number] = [next[0] - q[0], next[1] - q[1]];
    const qa: [number, number] = [q[0] - a[0], q[1] - a[1]];
    const denominator = cross(r, s);
    if (Math.abs(denominator) > 1e-12) {
      const t = cross(qa, s) / denominator;
      const u = cross(qa, r) / denominator;
      if (t >= -1e-10 && t <= 1 + 1e-10 && u >= -1e-10 && u <= 1 + 1e-10) measures.push(Math.max(0, Math.min(1, t)));
    } else if (denominatorR && Math.abs(cross(qa, r)) <= 1e-12 * Math.sqrt(denominatorR)) {
      [q, next].forEach(point => measures.push(Math.max(0, Math.min(1, ((point[0] - a[0]) * r[0] + (point[1] - a[1]) * r[1]) / denominatorR))));
    }
  });
  return measures;
};

const segmentInsidePolygon = (a: [number, number], b: [number, number], polygon: [number, number][][]) => {
  if (!pointInPolygon(a, polygon) || !pointInPolygon(b, polygon)) return false;
  const measures = [0, 1, ...polygon.flatMap(ring => ringIntersectionMeasures(a, b, ring))]
    .sort((first, second) => first - second)
    .filter((value, index, values) => index === 0 || Math.abs(value - values[index - 1]) > 1e-10);
  return measures.slice(0, -1).every((first, index) => {
    const middle = (first + measures[index + 1]) / 2;
    return pointInPolygon([a[0] + middle * (b[0] - a[0]), a[1] + middle * (b[1] - a[1])], polygon);
  });
};

export const lineInsideBoundary = (path: [number, number][], boundary: NonNullable<GisZoneGeometry['boundary']>) => {
  const polygons = boundary.type === 'MultiPolygon' ? boundary.coordinates as [number, number][][][] : [boundary.coordinates as [number, number][][]];
  return path.slice(0, -1).every((first, index) => polygons.some(polygon => segmentInsidePolygon(first, path[index + 1], polygon)));
};
