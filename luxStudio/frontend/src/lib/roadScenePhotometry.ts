import * as THREE from 'three';
import type { ConfigState } from '../store/useConfigStore';
import type { PhotometricDisplayUnit } from './visualization3d';
import type { RoadElement } from '../types';
import {
  computeCdAt,
  computeEAt,
  computeEvAt,
  effectiveMf,
  luminaireVisualTilt,
  photometricAnglesForRay,
  sampleIntensity,
} from './roadPhotometryMath';
import type { Photometric, PoleInfo } from './roadPhotometryMath';

export {
  computeCdAt,
  computeEAt,
  computeEvAt,
  effectiveMf,
  luminaireVisualTilt,
} from './roadPhotometryMath';
export type { Photometric, PoleInfo } from './roadPhotometryMath';

export type SceneCfg = Pick<ConfigState, 'arm_length' | 'arrangement' | 'height' | 'mf' | 'pole_count' | 'pole_offset' | 'pole_side' | 'road_width' | 'roadElements' | 'sidewalk_left' | 'sidewalk_right' | 'spacing' | 'tilt'>;

const LUX_GRADIENT = [
  { t: 0.0, c: new THREE.Color('#020617') },
  { t: 0.15, c: new THREE.Color('#1e1b4b') },
  { t: 0.3, c: new THREE.Color('#581c87') },
  { t: 0.45, c: new THREE.Color('#9a3412') },
  { t: 0.6, c: new THREE.Color('#facc15') },
  { t: 0.78, c: new THREE.Color('#fef08a') },
  { t: 1.0, c: new THREE.Color('#ffffff') },
];

export function sampleGradientColor(t: number): THREE.Color {
  const stops = LUX_GRADIENT;
  for (let k = 0; k < stops.length - 1; k++) {
    const a = stops[k];
    const b = stops[k + 1];
    if (t >= a.t && t <= b.t) {
      const f = (t - a.t) / (b.t - a.t);
      return a.c.clone().lerp(b.c, f);
    }
  }
  return stops[stops.length - 1].c.clone();
}

export function computeDisplayAt(px: number, pz: number, poles: PoleInfo[], p: Photometric, unit: PhotometricDisplayUnit, fluxScale: number = 1.0, mf: number = 1.0): number {
  return unit === 'lux' ? computeEAt(px, pz, poles, p, fluxScale, mf) : computeCdAt(px, pz, poles, p, fluxScale, mf);
}

function computeFieldStats(
  poles: PoleInfo[],
  p: Photometric,
  cfg: { road_width: number; sidewalk_left: number; sidewalk_right: number; spacing: number; pole_count: number },
  fluxScale: number = 1.0,
  mf: number = 1.0,
): { maxE: number; avgE: number; minE: number } {
  const W = cfg.road_width;
  const sl = cfg.sidewalk_left;
  const sr = cfg.sidewalk_right;
  const length = Math.max(cfg.spacing * Math.max(1, cfg.pole_count - 1) * 1.2, 30);
  const nx = 30;
  const nz = 10;
  const dx = length / nx;
  const dz = (W + sl + sr) / nz;
  const x0 = -length / 2;
  const z0 = -sl;
  const yFluxScale = (p.flux / 1000) * fluxScale * mf;
  let sum = 0;
  let minVal = Infinity;
  let maxVal = -Infinity;
  for (let i = 0; i < nx; i++) {
    const px2 = x0 + (i + 0.5) * dx;
    for (let j = 0; j < nz; j++) {
      const pz2 = z0 + (j + 0.5) * dz;
      let E2 = 0;
      for (const pole of poles) {
        const ax = px2 - pole.headX;
        const az2 = pz2 - pole.headZ;
        const ay2 = 0 - pole.headY;
        const d = Math.sqrt(ax * ax + ay2 * ay2 + az2 * az2);
        const angles = photometricAnglesForRay(pole, ax, ay2, az2);
        if (!angles) continue;
        const I = sampleIntensity(p, angles.c, angles.gamma);
        E2 += (I * yFluxScale * angles.cosG) / (d * d);
      }
      sum += E2;
      if (E2 < minVal) minVal = E2;
      if (E2 > maxVal) maxVal = E2;
    }
  }
  const total = nx * nz;
  return { maxE: maxVal, avgE: sum / total, minE: minVal };
}

export function computeDisplayStats(
  poles: PoleInfo[],
  p: Photometric,
  cfg: { road_width: number; sidewalk_left: number; sidewalk_right: number; spacing: number; pole_count: number },
  unit: PhotometricDisplayUnit,
  fluxScale: number = 1.0,
  mf: number = 1.0,
): { maxE: number; avgE: number; minE: number } {
  if (unit === 'lux') return computeFieldStats(poles, p, cfg, fluxScale, mf);
  const W = cfg.road_width;
  const sl = cfg.sidewalk_left;
  const sr = cfg.sidewalk_right;
  const length = Math.max(cfg.spacing * Math.max(1, cfg.pole_count - 1) * 1.2, 30);
  const nx = 25;
  const nz = 9;
  let sum = 0;
  let minVal = Infinity;
  let maxVal = -Infinity;
  for (let i = 0; i < nx; i++) {
    const px = -length / 2 + (i + 0.5) * (length / nx);
    for (let j = 0; j < nz; j++) {
      const pz = -sl + (j + 0.5) * ((W + sl + sr) / nz);
      const value = computeCdAt(px, pz, poles, p, fluxScale, mf);
      sum += value;
      if (value < minVal) minVal = value;
      if (value > maxVal) maxVal = value;
    }
  }
  return { maxE: maxVal, avgE: sum / (nx * nz), minE: minVal };
}

function _getCarriagewayEdge(elements: RoadElement[], side: 'left' | 'right'): number {
  if (side === 'left') {
    let z = 0;
    for (const el of elements) {
      if (el.type === 'carriageway') return z;
      z += el.width;
    }
    return 0;
  }
  let z = elements.reduce((s, e) => s + e.width, 0);
  for (let i = elements.length - 1; i >= 0; i--) {
    if (elements[i].type === 'carriageway') return z;
    z -= elements[i].width;
  }
  return z;
}

export function buildPoles(cfg: SceneCfg): PoleInfo[] {
  const S = cfg.spacing;
  const W = cfg.road_width;
  const arrangement = cfg.arrangement;
  const arm = cfg.arm_length;
  const tilt = (cfg.tilt * Math.PI) / 180;
  const h = cfg.height;
  const side = cfg.pole_side === 'right' ? 1 : -1;
  const n = cfg.pole_count;
  const half = (n - 1) / 2;
  const poles: PoleInfo[] = [];
  const elements = cfg.roadElements ?? [];

  const sideZ = (s: 'left' | 'right') => {
    const edge = _getCarriagewayEdge(elements, s);
    return s === 'left' ? edge - cfg.pole_offset : edge + cfg.pole_offset;
  };

  const placeRow = (xBase: number, zBase: number, sideSign: 1 | -1) => {
    const headX = xBase;
    const headY = h + arm * Math.sin(tilt);
    const headZ = zBase + sideSign * arm * Math.cos(tilt);
    const yaw = sideSign < 0 ? Math.PI : 0;
    poles.push({
      id: poles.length,
      baseX: xBase,
      baseZ: zBase,
      headX,
      headY,
      headZ,
      tiltRad: tilt,
      sideSign,
      cosYaw: Math.cos(-yaw),
      sinYaw: Math.sin(-yaw),
      cosTilt: Math.cos(tilt),
      sinTilt: Math.sin(tilt),
    });
  };

  if (arrangement === 'Lineal') {
    const zBase = sideZ(cfg.pole_side);
    const sideSign: 1 | -1 = side < 0 ? 1 : -1;
    for (let i = 0; i < n; i++) placeRow((i - half) * S, zBase, sideSign);
  } else if (arrangement === 'Bilateral') {
    const zL = sideZ('left');
    const zR = sideZ('right');
    for (let i = 0; i < n; i++) {
      placeRow((i - half) * S, zL, 1);
      placeRow((i - half) * S, zR, -1);
    }
  } else if (arrangement === 'Bilateral Alternada') {
    const zL = sideZ('left');
    const zR = sideZ('right');
    for (let i = 0; i < n; i++) {
      placeRow((i - half) * S, zL, 1);
      placeRow((i - half + 0.5) * S, zR, -1);
    }
  } else if (arrangement === 'Central Doble') {
    for (let i = 0; i < n; i++) {
      placeRow((i - half) * S, W / 2, 1);
      placeRow((i - half) * S, W / 2, -1);
    }
  } else if (arrangement === 'En Isleta') {
    for (let i = 0; i < n; i++) placeRow((i - half) * S, W / 2, 1);
  }
  return poles;
}
