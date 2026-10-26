import { readFileSync, existsSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { runInThisContext } from "node:vm";
import ts from "typescript";
const require = createRequire(import.meta.url);
const root = resolve(dirname(fileURLToPath(import.meta.url)), "../src");
export function loadComponent(relative, overrides = {}) {
  const cache = new Map();
  function load(file) {
    if (cache.has(file)) return cache.get(file).exports;
    const mod = { exports: {} }; cache.set(file, mod);
    const source = ts.transpileModule(readFileSync(file, "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true, target: ts.ScriptTarget.ES2022 } }).outputText;
    const localRequire = name => {
      if (Object.hasOwn(overrides, name)) return overrides[name];
      if (!name.startsWith(".") && !name.startsWith("@/")) return require(name);
      const stem = name.startsWith("@/") ? resolve(root, name.slice(2)) : resolve(dirname(file), name);
      return load([stem + ".ts", stem + ".tsx"].find(existsSync));
    };
    runInThisContext(`(function(require,module,exports){${source}\n})`, { filename: file })(localRequire, mod, mod.exports);
    return mod.exports;
  }
  return load(resolve(root, relative));
}
