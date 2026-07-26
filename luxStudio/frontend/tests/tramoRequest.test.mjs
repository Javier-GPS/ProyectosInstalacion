import assert from 'node:assert/strict';
import { mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { build } from 'esbuild';

const outdir = await mkdtemp(path.join(tmpdir(), 'lux-tramo-request-'));
const outfile = path.join(outdir, 'tramoRequest.mjs');
await build({
  entryPoints: [path.resolve('src/lib/tramoRequest.ts')],
  outfile,
  bundle: true,
  format: 'esm',
  platform: 'node',
});
const mod = await import(`file://${outfile.replaceAll('\\', '/')}`);

test('configHash produces stable JSON string', () => {
  const h = mod.configHash({ a: 1, b: 2 });
  assert.equal(typeof h, 'string');
  assert.equal(h, '{"a":1,"b":2}');
});

test('configHash differentiates different values', () => {
  const h1 = mod.configHash({ a: 1 });
  const h2 = mod.configHash({ a: 2 });
  assert.notEqual(h1, h2);
});

test('calculationConfigHash strips visual-only fields', () => {
  const full = {
    road_width: 7,
    illuminance_scale_mode: 'auto',
    illuminance_scale_min: 0,
    illuminance_scale_max: 50,
    photometric_display_unit: 'lux',
    generate_buildings: true,
    building_height: 12,
    buildings_as_obstacles: false,
    median_width: 0,
    language: 'es',
    __configHash: 'abc',
  };
  const h = mod.calculationConfigHash(full);
  assert.equal(h.includes('illuminance_scale_mode'), false);
  assert.equal(h.includes('language'), false);
  assert.equal(h.includes('__configHash'), false);
  assert.equal(h.includes('road_width'), true);
  assert.equal(h.includes('median_width'), false);
});

test('autoOptimizationConfigHash strips visual fields AND flux/power', () => {
  const full = {
    road_width: 7,
    target_flux: 12000,
    power: 100,
    illuminance_scale_mode: 'auto',
    __configHash: 'abc',
  };
  const h = mod.autoOptimizationConfigHash(full);
  assert.equal(h.includes('target_flux'), false);
  assert.equal(h.includes('power'), false);
  assert.equal(h.includes('illuminance_scale_mode'), false);
  assert.equal(h.includes('__configHash'), false);
  assert.equal(h.includes('road_width'), true);
});

test('withHash merges value with __configHash', () => {
  const result = mod.withHash({ a: 1 }, 'hash123');
  const parsed = JSON.parse(result);
  assert.equal(parsed.a, 1);
  assert.equal(parsed.__configHash, 'hash123');
});
