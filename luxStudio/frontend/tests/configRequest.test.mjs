import assert from 'node:assert/strict';
import { mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { build } from 'esbuild';

const outdir = await mkdtemp(path.join(tmpdir(), 'lux-config-request-'));
const outfile = path.join(outdir, 'configRequest.mjs');
await build({
  entryPoints: [path.resolve('src/lib/configRequest.ts')],
  outfile,
  bundle: true,
  format: 'esm',
  platform: 'node',
});
const mod = await import(`file://${outfile.replaceAll('\\', '/')}`);

test('buildCanonicalConfigRequest returns all fields from config', () => {
  const result = mod.buildCanonicalConfigRequest({
    road_width: 7,
    sidewalk_left: 1.5,
    sidewalk_right: 2,
    lanes: 2,
    arrangement: 'Lineal',
    height: 9,
    spacing: 30,
    arm_length: 1.5,
    pole_offset: 0,
    pole_side: 'left',
    tilt: 5,
    optic_family: 'F151',
    power: 100,
    target_flux: 12000,
    ldt_id: 'ldt-42',
    lighting_class: 'M3',
    mf: 0.85,
    pavement: 'R3',
    cct: 4000,
    cri: 70,
    language: 'es',
  });
  assert.equal(result.road_width, 7);
  assert.equal(result.arm_length, 1.5);
  assert.equal(result.tilt, 5);
  assert.equal(result.target_flux, 12000);
  assert.equal(result.armLength, 1.5);
  assert.equal(result.armTiltAngle, 5);
});

test('buildCanonicalConfigRequest resolves alias fields (armLength, armTiltAngle)', () => {
  const result = mod.buildCanonicalConfigRequest({
    road_width: 7,
    arrangement: 'Bilateral',
    height: 10,
    spacing: 35,
    armLength: 2,
    armTiltAngle: 3,
    lighting_class: 'M2',
    mf: 0.8,
    pavement: 'R2',
    cct: 3000,
    cri: 80,
  });
  assert.equal(result.arm_length, 2);
  assert.equal(result.tilt, 3);
});

test('buildCanonicalConfigRequest override takes precedence over config', () => {
  const result = mod.buildCanonicalConfigRequest(
    { road_width: 7, arrangement: 'Lineal', height: 9, spacing: 30, lighting_class: 'M3',
      mf: 0.85, pavement: 'R3', cct: 4000, cri: 70 },
    { road_width: 10, height: 12 },
  );
  assert.equal(result.road_width, 10);
  assert.equal(result.height, 12);
  assert.equal(result.spacing, 30);
});

test('buildCanonicalConfigRequest target_flux zero or negative becomes null', () => {
  const zero = mod.buildCanonicalConfigRequest({ target_flux: 0, road_width: 7, arrangement: 'Lineal',
    height: 9, spacing: 30, lighting_class: 'M3', mf: 0.85, pavement: 'R3', cct: 4000, cri: 70 });
  assert.equal(zero.target_flux, null);

  const neg = mod.buildCanonicalConfigRequest({ target_flux: -100, road_width: 7, arrangement: 'Lineal',
    height: 9, spacing: 30, lighting_class: 'M3', mf: 0.85, pavement: 'R3', cct: 4000, cri: 70 });
  assert.equal(neg.target_flux, null);
});

test('buildCanonicalConfigRequest missing fields become undefined', () => {
  const result = mod.buildCanonicalConfigRequest({
    road_width: 7,
    arrangement: 'Lineal',
    height: 9,
    spacing: 30,
    lighting_class: 'M3',
    mf: 0.85,
    pavement: 'R3',
    cct: 4000,
    cri: 70,
  });
  assert.equal(result.gama, undefined);
  assert.equal(result.difusor, undefined);
  assert.equal(result.lente, undefined);
  assert.equal(result.led_type, undefined);
});
