import { rValue } from './r_table';

export type Photometric = {
  id: string;
  c: number[];
  gamma: number[];
  intensity: number[][];
  conv: number;
  flux: number;
  power: number;
  Mc: number;
  Ng: number;
  isym: number;
  LORL: number;
  mf_origen?: number;
};

export type PoleInfo = {
  id: number;
  baseX: number;
  baseZ: number;
  headX: number;
  headY: number;
  headZ: number;
  tiltRad: number;
  sideSign: 1 | -1;
  cosYaw?: number;
  sinYaw?: number;
  cosTilt?: number;
  sinTilt?: number;
};

export const effectiveMf = (cfgMf: number, photometric: Photometric | null | undefined): number => {
  const origen = photometric?.mf_origen ?? 0.85;
  if (!origen || origen <= 0) return cfgMf;
  return cfgMf / origen;
};

export function luminaireVisualTilt(pole: PoleInfo): number {
  return -pole.tiltRad;
}

export function photometricAnglesForRay(
  pole: PoleInfo,
  ax: number,
  ay: number,
  az: number,
  distance?: number,
): { c: number; gamma: number; cosG: number } | null {
  const d = distance ?? Math.sqrt(ax * ax + ay * ay + az * az);
  if (d < 0.3) return null;

  const yaw = pole.sideSign < 0 ? Math.PI : 0;
  const cosY = pole.cosYaw ?? Math.cos(-yaw);
  const sinY = pole.sinYaw ?? Math.sin(-yaw);
  const xYaw = ax * cosY + az * sinY;
  const zYaw = -ax * sinY + az * cosY;

  const tilt = luminaireVisualTilt(pole);
  const cosT = pole.cosTilt ?? Math.cos(-tilt);
  const sinT = pole.sinTilt ?? Math.sin(-tilt);
  const yLocal = ay * cosT - zYaw * sinT;
  const zLocal = ay * sinT + zYaw * cosT;

  const cosG = -yLocal / d;
  if (cosG <= 0) return null;
  const gamma = (Math.acos(Math.min(1, Math.max(-1, cosG))) * 180) / Math.PI;
  if (gamma > 90) return null;
  const c = (Math.atan2(zLocal, xYaw) * 180) / Math.PI;
  return { c, gamma, cosG };
}

export function sampleIntensity(p: Photometric, cDeg: number, gammaDeg: number): number {
  const Mc = p.Mc;
  const Ng = p.Ng;
  const cStep = 360 / Mc;
  const gStep = 180 / (Ng - 1);
  const ci = (((cDeg % 360) + 360) % 360) / cStep;
  const c0 = Math.floor(ci) % Mc;
  const c1 = (c0 + 1) % Mc;
  const tc = ci - Math.floor(ci);
  const gClamped = Math.max(0, Math.min(180, gammaDeg));
  const gi = gClamped / gStep;
  const g0 = Math.max(0, Math.min(Ng - 1, Math.floor(gi)));
  const g1 = Math.max(0, Math.min(Ng - 1, g0 + 1));
  const tg = gi - g0;
  const v =
    (1 - tc) * (1 - tg) * p.intensity[c0][g0] +
    (1 - tc) * tg * p.intensity[c0][g1] +
    tc * (1 - tg) * p.intensity[c1][g0] +
    tc * tg * p.intensity[c1][g1];
  return Math.max(0, v) * p.conv;
}

export function computeEAt(
  px: number,
  pz: number,
  poles: PoleInfo[],
  p: Photometric,
  fluxScale: number = 1.0,
  mf: number = 1.0,
  py: number = 0,
): number {
  const yFluxScale = (p.flux / 1000) * fluxScale * mf;
  let E = 0;
  for (const pole of poles) {
    const ax = px - pole.headX;
    const az = pz - pole.headZ;
    const ay = py - pole.headY;
    const d2 = ax * ax + ay * ay + az * az;
    const d = Math.sqrt(d2);
    const angles = photometricAnglesForRay(pole, ax, ay, az, d);
    if (!angles) continue;
    const I = sampleIntensity(p, angles.c, angles.gamma);
    E += (I * yFluxScale * angles.cosG) / d2;
  }
  return E;
}

export function computeCdAt(
  px: number,
  pz: number,
  poles: PoleInfo[],
  p: Photometric,
  fluxScale: number = 1.0,
  mf: number = 1.0,
  obsX?: number,
  obsZ?: number,
): number {
  if (obsX === undefined) {
    let minX = Infinity;
    for (const pole of poles) minX = Math.min(minX, pole.headX);
    obsX = minX - 60;
  }
  if (obsZ === undefined) {
    let minZ = Infinity;
    let maxZ = -Infinity;
    for (const pole of poles) {
      minZ = Math.min(minZ, pole.headZ);
      maxZ = Math.max(maxZ, pole.headZ);
    }
    obsZ = (minZ + maxZ) / 2;
  }
  let L = 0;
  for (const pole of poles) {
    const ax = px - pole.headX;
    const az = pz - pole.headZ;
    const ay = -pole.headY;
    const d = Math.sqrt(ax * ax + ay * ay + az * az);
    const angles = photometricAnglesForRay(pole, ax, ay, az, d);
    if (!angles) continue;
    const I = sampleIntensity(p, angles.c, angles.gamma);
    const cd = I * (p.flux / 1000) * fluxScale * mf;
    const h = pole.headY;
    const tg = Math.sqrt(ax * ax + az * az) / h;
    const opx = px - obsX;
    const opz = pz - obsZ;
    const nOp = Math.hypot(opx, opz);
    const nLp = Math.hypot(ax, az);
    if (nOp < 1e-6 || nLp < 1e-6) continue;
    const cosTh = Math.max(-1, Math.min(1, (opx * ax + opz * az) / (nOp * nLp)));
    const beta = 180 - (Math.acos(cosTh) * 180) / Math.PI;
    L += (rValue(tg, beta) * cd) / (h * h);
  }
  return L;
}

export function computeEvAt(
  px: number,
  pz: number,
  poles: PoleInfo[],
  p: Photometric,
  fluxScale: number = 1.0,
  mf: number = 1.0,
  py: number = 0,
  normalZ: number = 1,
): number {
  const yFluxScale = (p.flux / 1000) * fluxScale * mf;
  let E = 0;
  for (const pole of poles) {
    const ax = px - pole.headX;
    const az = pz - pole.headZ;
    const ay = py - pole.headY;
    const d2 = ax * ax + ay * ay + az * az;
    const d = Math.sqrt(d2);
    if (d < 0.3) continue;
    const angles = photometricAnglesForRay(pole, ax, ay, az, d);
    if (!angles) continue;
    const I = sampleIntensity(p, angles.c, angles.gamma);
    const cosV = Math.max(0, Math.abs(normalZ * az) / d);
    E += (I * yFluxScale * cosV) / d2;
  }
  return E;
}
