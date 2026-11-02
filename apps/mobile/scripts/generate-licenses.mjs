#!/usr/bin/env node
/**
 * Builds lib/licenses.generated.json — the open-source packages the app
 * ships (package.json "dependencies", the web libraries in assets/vendor, and
 * the Lucide drawings) with their versions and licenses —
 * for Settings → Help & about → Open-source licenses.
 *
 * It runs on every `pnpm install` (postinstall), so the list always matches
 * node_modules and is not committed. `pnpm oss-licenses` runs it by hand.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const { dependencies } = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));

function licenseOf(pkg) {
  if (typeof pkg.license === "string") return pkg.license;
  if (pkg.license?.type) return pkg.license.type;
  if (Array.isArray(pkg.licenses)) return pkg.licenses.map((entry) => entry.type ?? entry).join(" OR ");
  return "UNKNOWN";
}

function installed(name) {
  const pkg = JSON.parse(readFileSync(join(root, "node_modules", name, "package.json"), "utf8"));
  return { name, version: pkg.version, license: licenseOf(pkg) };
}

// Shipped as assets by scripts/vendor-cdn.mjs; versions come from lib/vendor/manifest.json.
const { versions: vendored } = JSON.parse(
  readFileSync(join(root, "lib", "vendor", "manifest.json"), "utf8"),
);
const VENDORED = [
  ["katex", "katex", "MIT"],
  ["mermaid", "mermaid", "MIT"],
  ["pdfjs-dist", "pdfjs", "Apache-2.0"],
  ["smiles-drawer", "smilesDrawer", "MIT"],
  ["vega", "vega", "BSD-3-Clause"],
  ["vega-embed", "vegaEmbed", "BSD-3-Clause"],
  ["vega-lite", "vegaLite", "BSD-3-Clause"],
];

const packages = [
  ...Object.keys(dependencies).map(installed),
  ...VENDORED.filter(([name]) => !(name in dependencies)).map(([name, key, license]) => ({
    name,
    version: vendored[key],
    license,
  })),
  installed("lucide-static"),
].sort((a, b) => a.name.localeCompare(b.name));

writeFileSync(
  join(root, "lib", "licenses.generated.json"),
  `${JSON.stringify(packages, null, 2)}\n`,
);
console.log(`Wrote ${packages.length} packages.`);
