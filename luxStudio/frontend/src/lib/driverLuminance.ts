import { computeCdAt } from './roadPhotometryMath';
import type { Photometric, PoleInfo } from './roadPhotometryMath';

export interface DriverLuminanceSetup {
  poles: PoleInfo[];
  photometric: Photometric;
  fluxScale: number;
  mf: number;
  spacing: number;
  poleCount: number;
  textureWidth: number;
  textureHeight: number;
  worldLength: number;
  worldWidth: number;
  z0: number;
  color: [number, number, number];
}

export interface DriverLuminanceFrame {
  xStart: number;
  pixels: Uint8ClampedArray;
}

export function driverPoleCountForSpacing(spacing: number): number {
  const safeSpacing = Math.max(1, spacing);
  const worldLength = Math.max(140, safeSpacing * 8);
  const requiredPeriods = Math.ceil(worldLength / safeSpacing + 4);
  const oddPeriods = requiredPeriods % 2 === 0 ? requiredPeriods + 1 : requiredPeriods;
  return Math.max(9, oddPeriods);
}

export function renderDriverLuminanceFrame(
  setup: DriverLuminanceSetup,
  cameraX: number,
  cameraZ: number,
): DriverLuminanceFrame {
  const {
    poles,
    photometric,
    fluxScale,
    mf,
    spacing,
    poleCount,
    textureWidth,
    textureHeight,
    worldLength,
    worldWidth,
    z0,
    color,
  } = setup;
  const xStart = cameraX - worldLength * 0.25;
  const span = spacing * Math.max(1, poleCount);
  const xMid = xStart + worldLength / 2;
  const visibleDistance = worldLength / 2 + spacing * 2;
  const translatedPoles = poles
    .map((pole) => ({
      ...pole,
      baseX: pole.baseX + Math.round((xMid - pole.headX) / span) * span,
      headX: pole.headX + Math.round((xMid - pole.headX) / span) * span,
    }))
    .filter((pole) => Math.abs(pole.headX - xMid) < visibleDistance);

  const pixels = new Uint8ClampedArray(textureWidth * textureHeight * 4);
  const xDenominator = Math.max(1, textureWidth - 1);
  const yDenominator = Math.max(1, textureHeight - 1);
  for (let y = 0; y < textureHeight; y++) {
    const pz = z0 + (y / yDenominator) * worldWidth;
    for (let x = 0; x < textureWidth; x++) {
      const px = xStart + (x / xDenominator) * worldLength;
      const cd = computeCdAt(px, pz, translatedPoles, photometric, fluxScale, mf, cameraX, cameraZ);
      const tone = 1 - Math.exp(-Math.max(0, cd) * 1.35);
      const grain = 0.92 + 0.08 * Math.sin(px * 17.13 + pz * 31.7);
      const value = Math.min(255, Math.round((18 + tone * 210) * grain));
      const offset = (y * textureWidth + x) * 4;
      pixels[offset] = Math.round(color[0] * value);
      pixels[offset + 1] = Math.round(color[1] * value);
      pixels[offset + 2] = Math.round(color[2] * value);
      pixels[offset + 3] = Math.min(210, Math.round(18 + tone * 190));
    }
  }
  return { xStart, pixels };
}
