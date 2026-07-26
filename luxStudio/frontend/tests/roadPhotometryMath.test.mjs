import assert from 'node:assert/strict';
import { mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { build } from 'esbuild';

const outdir = await mkdtemp(path.join(tmpdir(), 'lux-road-photometry-'));
const outfile = path.join(outdir, 'roadPhotometryMath.mjs');
await build({
  entryPoints: [path.resolve('src/lib/roadPhotometryMath.ts')],
  outfile,
  bundle: true,
  format: 'esm',
  platform: 'node',
});
const mod = await import(`file://${outfile.replaceAll('\\', '/')}`);

const dummyPhotometric = {
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

const zeroPole = {
  id: 0, baseX: 0, baseZ: 0, headX: 0, headY: 9, headZ: 0,
  tiltRad: 0, sideSign: 1, cosYaw: 1, sinYaw: 0, cosTilt: 1, sinTilt: 0,
};

test('effectiveMf uses cfgMf / origen when origen is known', () => {
  const photometric = { ...dummyPhotometric, mf_origen: 0.85 };
  assert.equal(mod.effectiveMf(0.8, photometric), 0.8 / 0.85);
});

test('effectiveMf uses default 0.85 origen when photometric is null', () => {
  assert.equal(mod.effectiveMf(0.8, null), 0.8 / 0.85);
});

test('effectiveMf falls back to cfgMf when origen is 0', () => {
  const photometric = { ...dummyPhotometric, mf_origen: 0 };
  assert.equal(mod.effectiveMf(0.8, photometric), 0.8);
});

test('effectiveMf uses default 0.85 origen when photometric is undefined', () => {
  assert.equal(mod.effectiveMf(0.8, undefined), 0.8 / 0.85);
});

test('photometricAnglesForRay returns null for very close points', () => {
  assert.equal(mod.photometricAnglesForRay(zeroPole, 0, 0, 0, 0.1), null);
});

test('photometricAnglesForRay returns null when cosG <= 0 (point above pole)', () => {
  const result = mod.photometricAnglesForRay(zeroPole, 0, 20, 0);
  assert.equal(result, null);
});

test('photometricAnglesForRay returns null for gamma > 90', () => {
  const result = mod.photometricAnglesForRay(zeroPole, 0, 0.1, 50);
  assert.equal(result, null);
});

test('photometricAnglesForRay computes valid angles for point below pole', () => {
  const result = mod.photometricAnglesForRay(zeroPole, 5, -9, 0);
  assert(result !== null);
  assert.equal(typeof result.c, 'number');
  assert.equal(typeof result.gamma, 'number');
  assert(result.cosG > 0);
});

test('sampleIntensity bilinear interpolation at known coordinates', () => {
  const result = mod.sampleIntensity(dummyPhotometric, 0, 0);
  assert.equal(result, 120);
});

test('sampleIntensity handles out-of-range gamma by clamping to 90', () => {
  const result = mod.sampleIntensity(dummyPhotometric, 0, 180);
  assert(result >= 0);
});

test('computeEAt returns 0 for no poles', () => {
  assert.equal(mod.computeEAt(0, 0, [], dummyPhotometric), 0);
});

test('computeEAt returns positive illumination under a pole', () => {
  const E = mod.computeEAt(0, 0, [zeroPole], dummyPhotometric);
  assert(E > 0);
  assert(Number.isFinite(E));
});

test('computeCdAt returns non-negative luminance', () => {
  const L = mod.computeCdAt(0, 0, [zeroPole], dummyPhotometric, 1, 1, -60, 0);
  assert(L >= 0);
  assert(Number.isFinite(L));
});

test('computeEvAt returns non-negative vertical illuminance', () => {
  const Ev = mod.computeEvAt(0, 0, [zeroPole], dummyPhotometric, 1, 1, 0, 1);
  assert(Ev >= 0);
  assert(Number.isFinite(Ev));
});
