import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");

const exists = (relative) => fs.existsSync(path.join(root, relative));
const read = (relative) => fs.readFileSync(path.join(root, relative), "utf8");
const json = (relative) => JSON.parse(read(relative));

// El comité multi-agente (razonador + 8 subagentes + skills debate/razonamiento)
// vive en la config GLOBAL de opencode. Este proyecto NO debe contener copias
// locales que pisen a la global: si aparecen, el test falla (regresión).
const forbids = ["agent", "agents", "skills/debate", "skills/razonamiento"];
for (const f of forbids) {
  assert.ok(!exists(f), `No debe existir copia local del comité: ${f}`);
}

const packageJson = json("package.json");
const config = json("opencode.json");

// Sin agentes viejos ni nuevos inline en la config local (el global provee el comité).
for (const name of [
  "razonador",
  "analista",
  "arquitecto",
  "implementador",
  "critico",
  "revisor",
  "explorador",
  "saboteador",
  "concursante",
  "fiscal",
  "interprete",
  "jurado",
]) {
  assert.ok(!config.agent?.[name], `Agente local no debe existir: ${name}`);
}

assert.equal(config.default_agent, "razonador", "default_agent debe referenciar el razonador global");
assert.equal(config.skills?.paths?.includes(".opencode/skills"), true, "skills locales de proyecto");

assert.equal(packageJson.scripts?.["test:protocol"], "node tests/protocol-static.mjs");
assert.equal(packageJson.dependencies?.["@opencode-ai/plugin"], "1.17.11");
assert.ok(exists("package-lock.json"), "package-lock.json debe conservarse");

console.log("protocol-static: OK (sin copia local del comité; se usa la config global)");
