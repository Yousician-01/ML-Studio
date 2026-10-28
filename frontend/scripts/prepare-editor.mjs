// Serve Monaco and its workers from the local application, including offline use.
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { createRequire } from "node:module";
const root = fileURLToPath(new URL("../", import.meta.url));
const source = join(root, "node_modules", "monaco-editor");
if (!existsSync(join(source, "min", "vs", "loader.js"))) throw new Error("Install the pinned Monaco dependency before preparing editor assets.");
// Monaco embeds its sanitizer even in ESM: an npm override alone does not replace
// those bytes. Bundle ESM (not the prebuilt AMD editor) with the patched npm copy.
const require = createRequire(join(source, "package.json"));
const sanitizer = join(dirname(require.resolve("dompurify")), "purify.es.mjs");
if (!readFileSync(sanitizer, "utf8").includes("DOMPurify 3.4.17")) throw new Error("Expected the pinned patched DOMPurify version.");
cpSync(sanitizer, join(source, "esm", "vs", "base", "browser", "dompurify", "dompurify.js"));
const destination = join(root, "public", "monaco");
mkdirSync(destination, { recursive: true });
const assets = join(source, "min", "vs", "assets");
cpSync(assets, join(destination, "assets"), { recursive: true });
const workers = readdirSync(assets).filter(name => /^editor\.worker-.*\.js$/.test(name));
if (workers.length !== 1) throw new Error("Expected one pinned Monaco editor worker.");
cpSync(join(assets, workers[0]), join(destination, "assets", "editor.worker.js"));
for (const name of ["LICENSE", "ThirdPartyNotices.txt"]) cpSync(join(source, name), join(destination, name));
