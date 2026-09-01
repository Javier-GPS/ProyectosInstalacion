import type { LngLat } from './editorGeometry';
import type { ZoneAlignment } from '../store/slices/zonasSlice';

export const shiftLngLat = (coord: LngLat, a?: ZoneAlignment | null): LngLat =>
  !a || (a.dx === 0 && a.dy === 0) ? coord : [coord[0] + a.dx, coord[1] + a.dy];

export const unshiftLngLat = (coord: LngLat, a?: ZoneAlignment | null): LngLat =>
  !a || (a.dx === 0 && a.dy === 0) ? coord : [coord[0] - a.dx, coord[1] - a.dy];

export const shiftRing = (ring: LngLat[], a?: ZoneAlignment | null): LngLat[] =>
  !a || (a.dx === 0 && a.dy === 0) ? ring : ring.map(c => shiftLngLat(c, a));

export const shiftLine = (line: LngLat[], a?: ZoneAlignment | null): LngLat[] =>
  shiftRing(line, a);

export const shiftPolygon = (poly: { type: 'Polygon'; coordinates: LngLat[][] }, a?: ZoneAlignment | null) => {
  if (!a || (a.dx === 0 && a.dy === 0)) return poly;
  return { ...poly, coordinates: poly.coordinates.map(ring => shiftRing(ring, a)) };
};
