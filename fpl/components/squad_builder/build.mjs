import { build } from "esbuild";
import { cp, mkdir } from "node:fs/promises";

await mkdir("frontend_dist", { recursive: true });
await build({
  entryPoints: ["src/main.js"],
  bundle: true,
  minify: true,
  format: "iife",
  target: ["es2018"],
  outfile: "frontend_dist/main.js",
  logLevel: "info",
});
await cp("src/index.html", "frontend_dist/index.html");
await cp("src/style.css", "frontend_dist/style.css");
console.log("Squad builder frontend built -> frontend_dist/");
