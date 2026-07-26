import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");

const read = (relative) => {
  const file = path.join(root, relative);
  assert.ok(fs.existsSync(file), `Falta ${relative}`);
  return fs.readFileSync(file, "utf8");
};

const json = (relative) => JSON.parse(read(relative));
const has = (text, value, message = value) => assert.ok(text.includes(value), `Falta ${message}`);

const razonador = read("agent/razonador.md");
const debate = read("skills/debate/SKILL.md");
const razonamiento = read("skills/razonamiento/SKILL.md");
const arquitecto = read("agents/arquitecto.md");
const implementador = read("agents/implementador.md");
const revisor = read("agents/revisor.md");
const analista = read("agents/analista.md");
const packageJson = json("package.json");
const config = json("opencode.json");

assert.equal(
  [razonador, debate, razonamiento, arquitecto, implementador, revisor, analista]
    .join("\n")
    .split("RUN_LEDGER_PROTOCOL [NORMATIVE: RL1]").length - 1,
  1,
  "RL1 debe tener una sola fuente normativa"
);

for (const marker of [
  "### BEGIN_RUN_LEDGER",
  "### END_RUN_LEDGER",
  "writer=PRIMARY",
  "idempotency_key",
  "source_seq",
  "base_seq",
  "UNTRUSTED",
  "CLOSE_REQUEST",
  "PASS_PROTOCOL",
  "FUNCTIONAL_STATUS",
  "NOT_APPLICABLE",
  "Fase 0",
  "Fase 1",
  "Fase 2",
  "Fase 3",
  "Fase 4",
  "COMMITTEE",
  "plan_b",
]) has(razonador, marker);

for (const marker of [
  "GENERAR",
  "ATACAR",
  "DEFENDER",
  "REFINAR",
  "Fase 4: ejecución y cierre",
  "PRIMARY (edita y prueba)",
  "no editan",
]) has(debate, marker);

for (const marker of [
  "LIGHT",
  "FULL",
  "análisis-only",
  "UNVERIFIED",
  "plan_b",
  "BLOCKED",
]) has(razonamiento, marker);

for (const [name, text, markers] of [
  ["arquitecto", arquitecto, ["NORMATIVE:F2_HANDOFF", "obligations", "plan_b"]],
  ["implementador", implementador, ["NORMATIVE:F3_PLAN_CONTRACT", "E2E", "plan_b"]],
  ["revisor", revisor, ["NORMATIVE:F4_REVIEW_CONTRACT", "Fase 4", "UNVERIFIED"]],
  ["analista", analista, ["NORMATIVE:F4_CLOSE_AUTHORITY", "CLOSURE_DECISION", "PASS_PROTOCOL"]],
]) for (const marker of markers) has(text, marker, `${name}: ${marker}`);

assert.doesNotMatch(analista, /No participas en Fase 4/i, "Analista debe cerrar Fase 4");
assert.match(revisor, /Nunca (?:escribas|emitas)[\s\S]*PASS_PROTOCOL/i);
assert.match(implementador, /No editas, no ejecutas/i);
assert.match(razonador, /único escritor/i);

const frontmatter = (text, name) => {
  const match = text.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  assert.ok(match, `${name}: frontmatter ausente`);
  return match[1];
};

const primaryFrontmatter = frontmatter(razonador, "razonador");
assert.match(primaryFrontmatter, /mode:\s*primary/);
assert.match(primaryFrontmatter, /edit:\s*allow/);
assert.match(primaryFrontmatter, /bash:\s*ask/);

for (const [name, text] of [
  ["arquitecto", arquitecto],
  ["implementador", implementador],
  ["revisor", revisor],
  ["analista", analista],
]) {
  const fm = frontmatter(text, name);
  assert.match(fm, /mode:\s*subagent/, `${name}: mode inválido`);
  assert.match(fm, /edit:\s*deny/, `${name}: edit debe estar denegado`);
  assert.match(fm, /bash:\s*deny/, `${name}: bash debe estar denegado`);
  assert.match(fm, /read:\s*allow/, `${name}: read debe estar permitido`);
}

assert.equal(packageJson.scripts?.["test:protocol"], "node tests/protocol-static.mjs");
assert.equal(config.default_agent, "razonador");
assert.equal(config.skills?.paths?.includes(".opencode/skills"), true);
for (const agent of [
  "razonador",
  "analista",
  "arquitecto",
  "implementador",
  "critico",
  "revisor",
  "explorador",
  "saboteador",
]) assert.ok(config.agent?.[agent], `Agente no configurado: ${agent}`);

assert.equal(packageJson.dependencies?.["@opencode-ai/plugin"], "1.17.11");
assert.ok(fs.existsSync(path.join(root, "package-lock.json")), "package-lock.json debe conservarse");

console.log("protocol-static: OK");
