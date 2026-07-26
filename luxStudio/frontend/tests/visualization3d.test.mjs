import assert from 'node:assert/strict';
import { mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { build } from 'esbuild';

const outdir = await mkdtemp(path.join(tmpdir(), 'lux-visualization3d-'));
const outfile = path.join(outdir, 'visualization3d.mjs');

await build({
  entryPoints: [path.resolve('src/lib/visualization3d.ts')],
  outfile,
  bundle: true,
  format: 'esm',
  platform: 'node',
});

const mod = await import(`file://${outfile.replaceAll('\\', '/')}`);

test('manual scale remains fixed after values change', () => {
  const before = mod.resolveVisualizationScale('manual', 2, 20, [0, 5, 100]);
  const after = mod.resolveVisualizationScale('manual', 2, 20, [0, 80, 160]);
  assert.deepEqual(before, { min: 2, max: 20 });
  assert.deepEqual(after, before);
});

test('auto scale follows current values', () => {
  assert.deepEqual(mod.resolveVisualizationScale('auto', 2, 20, [1, 5, 9]), { min: 0, max: 9 });
  assert.deepEqual(mod.resolveVisualizationScale('auto', 2, 20, [1, 5, 40]), { min: 0, max: 40 });
});

test('buildings start after both sidewalks', () => {
  const rows = mod.buildBuildingRows({
    road_width: 7,
    sidewalk_left: 1.5,
    sidewalk_right: 2,
    spacing: 30,
    pole_count: 3,
    building_height: 14,
  });
  assert(rows.some((b) => b.id.startsWith('left-') && b.z < -1.5));
  assert(rows.some((b) => b.id.startsWith('right-') && b.z > 9));
});

test('power visual factor is bounded and does not affect calculations', () => {
  assert.equal(mod.powerVisualFactor(0), 0.6);
  assert(mod.powerVisualFactor(400) > mod.powerVisualFactor(100));
  assert.equal(mod.powerVisualFactor(10000), 1.8);
});

await writeFile(path.join(outdir, 'ok'), 'ok');
