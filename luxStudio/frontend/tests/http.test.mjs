import assert from 'node:assert/strict';
import { mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { build } from 'esbuild';

const outdir = await mkdtemp(path.join(tmpdir(), 'lux-http-'));
const outfile = path.join(outdir, 'http.mjs');
await build({
  entryPoints: [path.resolve('src/lib/http.ts')],
  outfile,
  bundle: true,
  format: 'esm',
  platform: 'node',
});
const mod = await import(`file://${outfile.replaceAll('\\', '/')}`);

test('requestJson parses structured API errors exactly once', async () => {
  const response = new Response(JSON.stringify({ detail: [{ msg: 'road_width is invalid' }] }), { status: 422 });
  await assert.rejects(
    () => mod.requestJson(async () => response, '/api/calculate', undefined, 'fallback'),
    { message: 'road_width is invalid' },
  );
});

test('extractError leaves the response body readable', async () => {
  const response = new Response(JSON.stringify({ detail: 'not authorized' }), { status: 401 });
  assert.equal(await mod.extractError(response, 'fallback'), 'not authorized');
  assert.deepEqual(await response.json(), { detail: 'not authorized' });
});

test('requestJson accepts empty successful responses', async () => {
  const result = await mod.requestJson(async () => new Response(null, { status: 204 }), '/api/delete', undefined, 'fallback');
  assert.equal(result, null);
});
