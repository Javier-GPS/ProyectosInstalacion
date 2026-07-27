import assert from 'node:assert/strict';
import test from 'node:test';
import { lineInsideBoundary, nearestInventoryHit, nearestLineHit, roadSelectionIsCurrent, sliceLine } from './roadSelection.ts';
import type { RoadSelectionDraft, RoadSelectionHit } from '../store/types';

const hit = (segment_index: number, segment_t: number, measure: number, coordinate: [number, number]): RoadSelectionHit =>
  ({ segment_index, segment_t, measure, coordinate });

test('nearestLineHit snaps within 12 pixels and rejects distant clicks', () => {
  const map = { project: ([x, y]: [number, number]) => ({ x: x * 100, y: y * 100 }) } as any;
  assert.deepEqual(nearestLineHit(map, [[0, 0], [1, 0]], { x: 50, y: 2 }), hit(0, 0.5, 0.5, [0.5, 0]));
  assert.equal(nearestLineHit(map, [[0, 0], [1, 0]], { x: 50, y: 20 }), null);
});

test('nearestInventoryHit selects the closest target and keeps its reference', () => {
  const map = { project: ([x, y]: [number, number]) => ({ x: x * 100, y: y * 100 }) } as any;
  const targets = [
    { target_ref: 'far', geometry: [[0, 0], [1, 0]] },
    { target_ref: 'near', geometry: [[0, 0.1], [1, 0.1]] },
  ] as any;
  assert.equal(nearestInventoryHit(map, targets, { x: 50, y: 9 })?.target_ref, 'near');
});

test('sliceLine preserves the requested direction and measures the clipped path', () => {
  const geometry: [number, number][] = [[0, 0], [0.001, 0], [0.002, 0]];
  const a = hit(0, 0.5, 0.25, [0.0005, 0]);
  const b = hit(1, 0.5, 0.75, [0.0015, 0]);
  const forward = sliceLine(geometry, a, b);
  const reverse = sliceLine(geometry, b, a);
  assert.deepEqual(forward?.path, [[0.0005, 0], [0.001, 0], [0.0015, 0]]);
  assert.deepEqual(reverse?.path, [...forward!.path].reverse());
  assert.ok(Math.abs(forward!.length_m - 111.2) < 0.2);
  assert.equal(sliceLine(geometry, a, a), null);
});

test('lineInsideBoundary supports polygons, holes and multipolygons', () => {
  const polygon: { type: 'Polygon'; coordinates: [number, number][][] } = { type: 'Polygon', coordinates: [[[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]]] };
  assert.equal(lineInsideBoundary([[0, 0], [0.5, 0]], polygon), true);
  assert.equal(lineInsideBoundary([[0, 0], [2, 0]], polygon), false);
  const withHole: { type: 'Polygon'; coordinates: [number, number][][] } = { type: 'Polygon', coordinates: [[[-2, -2], [2, -2], [2, 2], [-2, 2], [-2, -2]], [[-0.2, -0.2], [0.2, -0.2], [0.2, 0.2], [-0.2, 0.2], [-0.2, -0.2]]] };
  assert.equal(lineInsideBoundary([[-1, 0], [1, 0]], withHole), false);
  const narrowHole: { type: 'Polygon'; coordinates: [number, number][][] } = { type: 'Polygon', coordinates: [[[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]], [[0.00001, -0.00001], [0.00002, -0.00001], [0.00002, 0.00001], [0.00001, 0.00001], [0.00001, -0.00001]]] };
  assert.equal(lineInsideBoundary([[-0.001, 0], [0.001, 0]], narrowHole), false);
  const multi: { type: 'MultiPolygon'; coordinates: [number, number][][][] } = { type: 'MultiPolygon', coordinates: [polygon.coordinates, [[[3, 3], [4, 3], [4, 4], [3, 4], [3, 3]]]] };
  assert.equal(lineInsideBoundary([[3.2, 3.2], [3.8, 3.8]], multi), true);
});

test('road selection is invalidated by inventory, boundary or target changes', () => {
  const boundary: { type: 'Polygon'; coordinates: [number, number][][] } = { type: 'Polygon', coordinates: [[[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]]] };
  const draft: RoadSelectionDraft = {
    zone_id: 'z', inventory_hash: 'hash', boundary_signature: JSON.stringify(boundary), status: 'complete', area_points: [], boundary,
    a: { target_ref: 'target', segment_index: 0, segment_t: 0.5, measure: 0.5, coordinate: [0, 0] },
  };
  const inventory = { base_inventory_hash: 'hash', targets: [{ target_ref: 'target' }] } as any;
  assert.equal(roadSelectionIsCurrent(draft, inventory, boundary), true);
  assert.equal(roadSelectionIsCurrent(draft, { ...inventory, base_inventory_hash: 'other' }, boundary), false);
  assert.equal(roadSelectionIsCurrent(draft, { ...inventory, targets: [] }, boundary), false);
  assert.equal(roadSelectionIsCurrent(draft, inventory, { ...boundary, coordinates: [[[-2, -2], [2, -2], [2, 2], [-2, 2], [-2, -2]]] }), false);
});
