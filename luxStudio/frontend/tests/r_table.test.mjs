import assert from 'node:assert/strict';
import { mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { build } from 'esbuild';

const outdir = await mkdtemp(path.join(tmpdir(), 'lux-r-table-'));
const outfile = path.join(outdir, 'r_table.mjs');
await build({
  entryPoints: [path.resolve('src/lib/r_table.ts')],
  outfile,
  bundle: true,
  format: 'esm',
  platform: 'node',
});
const mod = await import(`file://${outfile.replaceAll('\\', '/')}`);

test('rValue at exact table coordinates returns the expected value', () => {
  const v = mod.rValue(0, 0);
  assert.equal(v, 294 / 10000);
});

test('rValue is symmetric for beta', () => {
  const v1 = mod.rValue(1, 15);
  const v2 = mod.rValue(1, -15);
  assert.equal(v1, v2);
});

test('rValue wraps beta beyond 180', () => {
  const v1 = mod.rValue(1, 200);
  const v2 = mod.rValue(1, 160);
  assert.equal(v1, v2);
});

test('rValue returns 0 for geometrically invalid regions', () => {
  const v = mod.rValue(5.5, 60);
  assert.equal(v, 0);
});

test('rValue clamps tg to 0..12', () => {
  const vNeg = mod.rValue(-1, 0);
  const vPos = mod.rValue(0, 0);
  assert.equal(vNeg, vPos);

  const vOver = mod.rValue(15, 0);
  const vMax = mod.rValue(12, 0);
  assert.equal(vOver, vMax);
});

test('rValue interpolates between table entries', () => {
  const at2 = mod.rValue(2, 0);
  assert(at2 > 0);

  const mid = mod.rValue(1.5, 0);
  assert(mid > 0);
  assert(mid !== at2);
});
