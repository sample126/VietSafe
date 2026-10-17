import { copyFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const frontendVendor = path.join(root, "frontend", "vendor");
mkdirSync(frontendVendor, { recursive: true });

await build({
  entryPoints: [path.join(root, "frontend", "js", "vector-map-vendor.js")],
  outfile: path.join(frontendVendor, "vector-map.js"),
  bundle: true,
  minify: true,
  format: "iife",
  alias: { leaflet: path.join(root, "frontend", "js", "leaflet-global.js") },
});

const assets = [
  ["node_modules/maplibre-gl/dist/maplibre-gl-worker.mjs", "maplibre-gl-worker.mjs"],
  ["node_modules/maplibre-gl/dist/maplibre-gl.css", "maplibre-gl.css"],
  ["node_modules/maplibre-gl/LICENSE.txt", "MAPLIBRE-LICENSE.txt"],
  ["node_modules/@maplibre/maplibre-gl-leaflet/LICENSE", "MAPLIBRE-LEAFLET-LICENSE.txt"],
];
for (const [source, name] of assets) {
  copyFileSync(path.join(root, source), path.join(frontendVendor, name));
}

const publicVendor = path.join(root, "public", "vendor");
mkdirSync(publicVendor, { recursive: true });
for (const name of ["vector-map.js", ...assets.map(([, name]) => name)]) {
  copyFileSync(path.join(frontendVendor, name), path.join(publicVendor, name));
}
