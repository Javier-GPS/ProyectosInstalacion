import assert from 'node:assert/strict';
import { mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { build } from 'esbuild';

const outdir = await mkdtemp(path.join(tmpdir(), 'lux-driver-luminance-'));
const outfile = path.join(outdir, 'driver-luminance.mjs');

await build({
  entryPoints: [path.resolve('src/lib/driverLuminance.ts')],
  outfile,
  bundle: true,
  format: 'esm',
  platform: 'node',
});

const mod = await import(`file://${outfile.replaceAll('\\', '/')}`);

const photometric = {
  id: 'test',
  c: [0, 90, 180, 270],
  gamma: [0, 45, 90],
  intensity: [[120, 90, 20], [110, 80, 15], [100, 70, 10], [110, 80, 15]],
  conv: 1,
  flux: 10_000,
  power: 100,
  Mc: 4,
  Ng: 3,
  isym: 0,
  LORL: 1,
};

function makeSetup(spacing = 30) {
  const poleCount = mod.driverPoleCountForSpacing(spacing);
  const half = (poleCount - 1) / 2;
  const poles = Array.from({ length: poleCount }, (_, index) => ({
    id: index,
    baseX: (index - half) * spacing,
    baseZ: -1,
    headX: (index - half) * spacing,
    headY: 9,
    headZ: 0,
    tiltRad: 0,
    sideSign: 1,
    cosYaw: 1,
    sinYaw: 0,
    cosTilt: 1,
    sinTilt: 0,
  }));
  return {
    poles,
    photometric,
    fluxScale: 1,
    mf: 0.8,
    spacing,
    poleCount,
    textureWidth: 24,
    textureHeight: 8,
    worldLength: Math.max(140, spacing * 8),
    worldWidth: 10,
    z0: -2,
    color: [1, 0.9, 0.75],
  };
}

test('uses only the pole periods needed by the visible Driver window', () => {
  assert.equal(mod.driverPoleCountForSpacing(30), 13);
  assert.equal(mod.driverPoleCountForSpacing(60), 13);
  assert.equal(mod.driverPoleCountForSpacing(5), 33);
});

test('renders the complete deterministic CIE luminance frame', () => {
  const setup = makeSetup();
  const first = mod.renderDriverLuminanceFrame(setup, 0, 3.5);
  const second = mod.renderDriverLuminanceFrame(setup, 0, 3.5);

  assert.equal(first.xStart, -60);
  assert.equal(first.pixels.length, setup.textureWidth * setup.textureHeight * 4);
  assert.deepEqual(first.pixels, second.pixels);
  assert(first.pixels.some((value, index) => index % 4 !== 3 && value > 20));
  assert(first.pixels.every((value) => Number.isFinite(value)));
});

test('keeps the periodic photometric field populated after long travel', () => {
  const setup = makeSetup();
  const start = mod.renderDriverLuminanceFrame(setup, 0, 3.5);
  const travelled = mod.renderDriverLuminanceFrame(setup, setup.spacing * setup.poleCount * 9, 3.5);

  const startAlpha = Array.from(start.pixels).filter((_, index) => index % 4 === 3);
  const travelledAlpha = Array.from(travelled.pixels).filter((_, index) => index % 4 === 3);
  assert.deepEqual(travelledAlpha, startAlpha);
});
