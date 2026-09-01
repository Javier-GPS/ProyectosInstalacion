/** Utilidades geométricas para el editor de ciudad.
 *  Trabajan en [lng, lat] y convierten metros a grados de forma aproximada. */

export type LngLat = [number, number];

const M_PER_DEG_LAT = 111320;

export const metersToDeg = (lat: number): { dLat: number; dLng: number } => ({
  dLat: 1 / M_PER_DEG_LAT,
  dLng: 1 / (M_PER_DEG_LAT * Math.cos((lat * Math.PI) / 180 || 1e-6)),
});

const unitDir = (a: LngLat, b: LngLat): LngLat => {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len = Math.hypot(dx, dy) || 1e-9;
  return [dx / len, dy / len];
};

/** Polilínea desplazada `offsetMeters` al lado izquierdo de la línea central.
 *  offset positivo = izquierda, negativo = derecha (en metros). */
export const offsetEdge = (geom: LngLat[], offsetMeters: number): LngLat[] => {
  if (geom.length < 2) return [];
  const pts: LngLat[] = [];
  for (let i = 0; i < geom.length; i++) {
    const prev = geom[i - 1] ?? geom[i];
    const next = geom[i + 1] ?? geom[i];
    const dir = unitDir(prev, next);
    const nx = -dir[1];
    const ny = dir[0];
    const { dLat, dLng } = metersToDeg(geom[i][1]);
    pts.push([geom[i][0] + nx * offsetMeters * dLng, geom[i][1] + ny * offsetMeters * dLat]);
  }
  return pts;
};

/** Anillo de polígono (cerrado) para una calzada de `widthMeters` centrada en `geom`. */
export const roadPolygon = (geom: LngLat[], widthMeters: number): LngLat[] => {
  if (geom.length < 2) return [];
  const half = widthMeters / 2;
  const left = offsetEdge(geom, half);
  const right = offsetEdge(geom, -half);
  const ring = [...left, ...right.reverse()];
  ring.push(left[0]);
  return ring;
};

/** Aceras: devuelve los anillos izquierdo y derecho a partir del ancho de calzada
 *  y los anchos de acera. */
export const sidewalkPolygons = (
  geom: LngLat[],
  roadWidth: number,
  swLeft?: number | null,
  swRight?: number | null,
): LngLat[][] => {
  const rings: LngLat[][] = [];
  if (geom.length < 2) return rings;
  const halfRoad = roadWidth / 2;
  if (swLeft && swLeft > 0) {
    const inner = offsetEdge(geom, halfRoad);
    const outer = offsetEdge(geom, halfRoad + swLeft);
    const ring = [...inner, ...outer.reverse()];
    ring.push(inner[0]);
    rings.push(ring);
  }
  if (swRight && swRight > 0) {
    const inner = offsetEdge(geom, -halfRoad);
    const outer = offsetEdge(geom, -(halfRoad + swRight));
    const ring = [...outer, ...inner.reverse()];
    ring.push(outer[0]);
    rings.push(ring);
  }
  return rings;
};

/** Anillo rectangular (cerrado) centrado en (lng,lat), dimensiones en metros,
 *  rotado `rotationDeg` grados. */
export const rotateFootprint = (
  lng: number,
  lat: number,
  width: number,
  length: number,
  rotationDeg: number,
): LngLat[] => {
  const { dLat, dLng } = metersToDeg(lat);
  const hw = width / 2;
  const hl = length / 2;
  const rad = (rotationDeg * Math.PI) / 180;
  const cos = Math.cos(rad);
  const sin = Math.sin(rad);
  const corners: [number, number][] = [
    [-hw, -hl],
    [hw, -hl],
    [hw, hl],
    [-hw, hl],
  ];
  const ring = corners.map(([x, y]) => {
    const rx = x * cos - y * sin;
    const ry = x * sin + y * cos;
    return [lng + rx * dLng, lat + ry * dLat] as LngLat;
  });
  ring.push(ring[0]);
  return ring;
};

/** Devuelve [west, south, east, north] para un conjunto de coordenadas. */
export const bboxOf = (coords: LngLat[]): [number, number, number, number] => {
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
  for (const [x, y] of coords) {
    if (x < w) w = x;
    if (y < s) s = y;
    if (x > e) e = x;
    if (y > n) n = y;
  }
  return [w, s, e, n];
};

export const bboxOfMany = (rings: LngLat[][]): [number, number, number, number] => {
  const all: LngLat[] = [];
  for (const r of rings) all.push(...r);
  return bboxOf(all);
};

/** Pseudo-altura estable para edificios a partir de su centroide. */
export const buildingHeight = (ring: LngLat[]): number => {
  let lon = 0, lat = 0;
  const n = Math.max(1, ring.length - 1);
  for (let i = 0; i < n; i++) { lon += ring[i][0]; lat += ring[i][1]; }
  const seed = Math.abs(Math.sin(lon * 12.9898 + lat * 78.233) * 43758.5453);
  const frac = seed - Math.floor(seed);
  return 5 + Math.round(frac * 14); // 5–19 m
};

/** Extrae anillos de edificio (GeoJSON Polygon/MultiPolygon) de forma tolerante. */
export const parseBuildings = (raw: unknown): LngLat[][] => {
  if (!Array.isArray(raw)) return [];
  const rings: LngLat[][] = [];
  for (const item of raw) {
    try {
      const geom = (item as any)?.geometry ?? item;
      const type = geom?.type;
      if (type === 'Polygon' && Array.isArray(geom.coordinates)) {
        const ring = geom.coordinates[0] as LngLat[];
        if (ring?.length >= 3) rings.push(ring);
      } else if (type === 'MultiPolygon' && Array.isArray(geom.coordinates)) {
        for (const poly of geom.coordinates as LngLat[][][]) {
          if (poly?.[0]?.length >= 3) rings.push(poly[0]);
        }
      }
    } catch { /* skip */ }
  }
  return rings;
};

/** Longitud en metros de una polilínea [lng,lat] (aproximación local). */
const segMeters = (a: LngLat, b: LngLat): number => {
  const { dLat, dLng } = metersToDeg(a[1]);
  const dx = (b[0] - a[0]) / dLng;
  const dy = (b[1] - a[1]) / dLat;
  return Math.hypot(dx, dy);
};

export const lineLengthM = (geom: LngLat[]): number => {
  let total = 0;
  for (let i = 0; i < geom.length - 1; i++) total += segMeters(geom[i], geom[i + 1]);
  return total;
};

export interface LineSample {
  point: LngLat;
  /** Rumbo local en grados (road heading). */
  headingDeg: number;
  /** Normal izquierda unitaria en espacio de grados (para retranqueos). */
  lNormal: [number, number];
}

/** Punto a `meters` a lo largo de la polilínea con rumbo y normal lateral. Rectifica al extremo. */
export const pointAlongLine = (geom: LngLat[], meters: number): LineSample | null => {
  if (!geom.length) return null;
  if (geom.length === 1) return { point: geom[0], headingDeg: 0, lNormal: [0, 0] };
  let travelled = 0;
  for (let i = 0; i < geom.length - 1; i++) {
    const a = geom[i];
    const b = geom[i + 1];
    const s = segMeters(a, b);
    if (travelled + s >= meters) {
      const t = s ? Math.max(0, Math.min(1, (meters - travelled) / s)) : 0;
      const lng = a[0] + t * (b[0] - a[0]);
      const lat = a[1] + t * (b[1] - a[1]);
      const dx = b[0] - a[0];
      const dy = b[1] - a[1];
      const n = Math.hypot(dx, dy) || 1e-9;
      return { point: [lng, lat], headingDeg: Math.atan2(dy, dx) * 180 / Math.PI, lNormal: [-dy / n, dx / n] };
    }
    travelled += s;
  }
  const last = geom[geom.length - 1];
  const prev = geom[geom.length - 2];
  const dx = last[0] - prev[0];
  const dy = last[1] - prev[1];
  const n = Math.hypot(dx, dy) || 1e-9;
  return { point: last, headingDeg: Math.atan2(dy, dx) * 180 / Math.PI, lNormal: [-dy / n, dx / n] };
};

/** Desplaza un sample lateralmente `meters` (positivo = izquierda) usando grados/m. */
export const lateralOffsetPoint = (sample: LineSample, meters: number): LngLat => {
  const { dLat, dLng } = metersToDeg(sample.point[1]);
  return [sample.point[0] + sample.lNormal[0] * meters * dLng, sample.point[1] + sample.lNormal[1] * meters * dLat];
};

export type FarolaDistribution =
  | 'unilateral_r' | 'unilateral_l' | 'bilateral_pareado'
  | 'bilateral_tresbolillo' | 'centrada_mediana' | 'mediana_compartida';

export interface FarolaRouteOpts {
  spacing: number;
  /** Distancia despejada a cruces (no colocar en los extremos). */
  clearance: number;
  /** Retranqueo desde el borde de calzada (m). */
  setback: number;
  distribution: FarolaDistribution;
  /** Semiancho de calzada (m). */
  roadHalfWidth: number;
  /** Polígonos de calzadas que cruzan (para no caer sobre el asfalto). */
  asphaltRings?: LngLat[][];
}

export interface FarolaPlacement {
  point: LngLat;
  rotation: number;
  side: 'left' | 'right' | 'center';
}

/** Autoposiciona farolas a lo largo de una polilínea respetando distribución y retranqueo.
 *  Evita caer sobre el asfalto de calzadas que cruzan: si un punto cae en un cruce, se
 *  retrasa hasta la acera justo antes del asfalto y se continúa con la misma interdistancia. */
export const placeFarolasAlong = (geom: LngLat[], opts: FarolaRouteOpts): FarolaPlacement[] => {
  const length = lineLengthM(geom);
  const spacing = Math.max(1, opts.spacing);
  const clearance = Math.max(0, opts.clearance);
  if (length <= clearance * 2 + spacing) return [];
  const half = opts.roadHalfWidth + Math.max(0, opts.setback);
  const rings = opts.asphaltRings || [];
  const onAsphalt = (p: LngLat) => rings.some(r => pointInPolygon(p, r));
  const sideOffsets = (i: number): { side: FarolaPlacement['side']; latOff: number }[] => {
    const d = opts.distribution;
    if (d === 'centrada_mediana' || d === 'mediana_compartida') return [{ side: 'center', latOff: 0 }];
    if (d === 'unilateral_r') return [{ side: 'right', latOff: -half }];
    if (d === 'unilateral_l') return [{ side: 'left', latOff: half }];
    if (d === 'bilateral_pareado') return [{ side: 'left', latOff: half }, { side: 'right', latOff: -half }];
    if (d === 'bilateral_tresbolillo') { const side = i % 2 === 0 ? 'left' : 'right'; return [{ side, latOff: side === 'left' ? half : -half }]; }
    return [{ side: 'right', latOff: -half }];
  };
  const pointAt = (s: number, latOff: number): LngLat | null => {
    const sample = pointAlongLine(geom, s);
    return sample ? lateralOffsetPoint(sample, latOff) : null;
  };
  // Si un punto cae sobre asfalto (cruce), retrasa la estación hasta dejarlo libre un poco antes.
  const clearStation = (s: number, offsets: { side: FarolaPlacement['side']; latOff: number }[]): number | null => {
    const onObstacle = (x: number) => offsets.some(o => { const p = pointAt(x, o.latOff); return !!p && onAsphalt(p); });
    if (!onObstacle(s)) return s;
    let st = s;
    let guard = 0;
    while (st > clearance && onObstacle(st) && guard < 120) { st -= 0.25; guard++; }
    if (st - 1 < clearance || guard >= 120) return null;
    return st - 1;
  };
  const items: FarolaPlacement[] = [];
  let lastPlacedS = -Infinity;
  let i = 0;
  for (let s = clearance; s <= length - clearance; s += spacing, i++) {
    const offsets = sideOffsets(i);
    const station = clearStation(s, offsets);
    if (station == null || station - lastPlacedS <= 1) continue;
    for (const o of offsets) {
      const sample = pointAlongLine(geom, station);
      if (sample) items.push({ point: lateralOffsetPoint(sample, o.latOff), rotation: sample.headingDeg, side: o.side });
    }
    lastPlacedS = station;
  }
  return items;
};

export interface StreetSegment {
  ref: string;
  geom: LngLat[];
}

const segEnds = (geom: LngLat[]): LngLat[] => [geom[0], geom[geom.length - 1]];

/** Tolerancia de conexión entre extremos de tramos (~1 cm). */
const CONN_EPS = 1e-7;

const segsConnected = (a: LngLat[], b: LngLat[]) => {
  for (const ea of segEnds(a)) for (const eb of segEnds(b)) {
    if (Math.hypot(ea[0] - eb[0], ea[1] - eb[1]) < CONN_EPS) return true;
  }
  return false;
};

/** Camino de `ref`s conectados entre dos tramos de la misma calle, o null si no hay conexión. */
export const connectStreetSegments = (segments: StreetSegment[], aRef: string, bRef: string): string[] | null => {
  if (aRef === bRef) return [aRef];
  const byRef = new Map(segments.map(s => [s.ref, s]));
  if (!byRef.has(aRef) || !byRef.has(bRef)) return null;
  const queue: { ref: string; chain: string[] }[] = [{ ref: aRef, chain: [aRef] }];
  const visited = new Set<string>([aRef]);
  while (queue.length) {
    const { ref, chain } = queue.shift()!;
    const geom = byRef.get(ref)!.geom;
    for (const s of segments) {
      if (visited.has(s.ref)) continue;
      if (!segsConnected(geom, s.geom)) continue;
      const nextChain = [...chain, s.ref];
      if (s.ref === bRef) return nextChain;
      visited.add(s.ref);
      queue.push({ ref: s.ref, chain: nextChain });
    }
  }
  return null;
};

/** Construye la polilínea continua desde el punto A hasta el punto B a lo largo del camino de tramos. */
export const joinStreetPath = (
  segments: StreetSegment[],
  chain: string[],
  a: { measure: number; coordinate: LngLat },
  b: { measure: number; coordinate: LngLat },
): LngLat[] | null => {
  const byRef = new Map(segments.map(s => [s.ref, s]));
  const geoms = chain.map(ref => byRef.get(ref)?.geom);
  if (geoms.some(g => !g || g.length < 2)) return null;
  const near = (p: LngLat, q: LngLat) => Math.hypot(p[0] - q[0], p[1] - q[1]) < CONN_EPS;
  const end = (g: LngLat[]) => g[g.length - 1];
  const nearestIdx = (g: LngLat[], p: LngLat) => {
    let best = 0, bestD = Infinity;
    for (let i = 0; i < g.length; i++) {
      const d = Math.hypot(g[i][0] - p[0], g[i][1] - p[1]);
      if (d < bestD) { bestD = d; best = i; }
    }
    return best;
  };
  // Porción de un tramo desde `cut` hasta su extremo (forward) o su inicio (backward).
  const cutFrom = (g: LngLat[], cut: LngLat, forward: boolean): LngLat[] => {
    const ni = nearestIdx(g, cut);
    const isV = near(g[ni], cut);
    return forward
      ? (isV ? g.slice(ni) : [cut, ...g.slice(ni + 1)])
      : (isV ? g.slice(0, ni + 1).reverse() : [cut, ...g.slice(0, ni).reverse()]);
  };
  // Porción de un tramo desde su extremo (forward) o su inicio (backward) hasta `cut`.
  const cutTo = (g: LngLat[], cut: LngLat, forward: boolean): LngLat[] => {
    const ni = nearestIdx(g, cut);
    const isV = near(g[ni], cut);
    return forward
      ? (isV ? g.slice(0, ni + 1) : [...g.slice(0, ni), cut])
      : (isV ? g.slice(ni).reverse() : [...g.slice(ni + 1).reverse(), cut]);
  };
  const path: LngLat[] = [];
  const pushPts = (pts: LngLat[]) => {
    for (const p of pts) {
      if (!path.length || !near(path[path.length - 1], p)) path.push(p);
    }
  };
  for (let i = 0; i < chain.length; i++) {
    const geom = geoms[i] as LngLat[];
    const isLast = i === chain.length - 1;
    let forward: boolean;
    if (i === 0 && !isLast) {
      const next = geoms[1] as LngLat[];
      forward = near(end(geom), next[0]) || near(end(geom), end(next));
    } else if (isLast && i > 0) {
      const prevLast = path[path.length - 1];
      forward = near(geom[0], prevLast);
    } else {
      forward = b.measure >= a.measure;
    }
    if (i === 0 && isLast) {
      // Un único tramo: porción entre A y B.
      const na = nearestIdx(geom, a.coordinate);
      const nb = nearestIdx(geom, b.coordinate);
      const va = near(geom[na], a.coordinate);
      const vb = near(geom[nb], b.coordinate);
      const pts = forward
        ? [va ? geom[na] : a.coordinate, ...geom.slice(na + 1, nb), vb ? geom[nb] : b.coordinate]
        : [va ? geom[na] : a.coordinate, ...geom.slice(nb + 1, na).reverse(), vb ? geom[nb] : b.coordinate];
      pushPts(pts);
    } else if (i === 0) {
      pushPts(cutFrom(geom, a.coordinate, forward));
    } else if (isLast) {
      pushPts(cutTo(geom, b.coordinate, forward));
    } else {
      pushPts(forward ? geom : [...geom].reverse());
    }
  }
  return path;
};

/** Ray-casting point-in-polygon. `ring` es una polilínea cerrada [lng,lat]. */
export const pointInPolygon = (pt: LngLat, ring: LngLat[]): boolean => {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0], yi = ring[i][1];
    const xj = ring[j][0], yj = ring[j][1];
    const intersect = (yi > pt[1]) !== (yj > pt[1]) &&
      pt[0] < ((xj - xi) * (pt[1] - yi)) / (yj - yi + 1e-12) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
};

/** Extrae puntos [lng,lat] de árboles de forma tolerante. */
export const parseTrees = (raw: unknown): LngLat[] => {
  if (!Array.isArray(raw)) return [];
  const pts: LngLat[] = [];
  for (const item of raw) {
    const o = item as any;
    let lng: number | undefined, lat: number | undefined;
    if (typeof o?.lon === 'number' && typeof o?.lat === 'number') { lng = o.lon; lat = o.lat; }
    else if (typeof o?.lng === 'number' && typeof o?.lat === 'number') { lng = o.lng; lat = o.lat; }
    else if (typeof o?.x === 'number' && typeof o?.y === 'number') { lng = o.x; lat = o.y; }
    else if (Array.isArray(o?.geometry) && o.geometry.length === 2) { lng = o.geometry[0]; lat = o.geometry[1]; }
    else if (Array.isArray(o) && o.length === 2 && typeof o[0] === 'number') { lng = o[0]; lat = o[1]; }
    if (typeof lng === 'number' && typeof lat === 'number') pts.push([lng, lat]);
  }
  return pts;
};
