#!/usr/bin/env node
/**
 * Vendor CDN-served JS/CSS/font assets into local files so the sandboxed
 * WebView renderers (KaTeX, Mermaid, Vega, pdf.js, SmilesDrawer) work fully
 * offline — no runtime CDN fetch, tighter CSP, faster first render.
 *
 * KaTeX CSS/fonts follow the installed mobile renderer. Other versions remain pinned.
 *
 * Output: apps/mobile/lib/vendor/*.txt  (committed; this script regenerates them).
 * Each file is the library's own text. Metro ships them as assets beside the JS
 * bundle ("txt" in apps/mobile/metro.config.js); apps/mobile/lib/vendorAssets.ts
 * names each one and reads it at run time.
 *
 * Usage: node scripts/vendor-cdn.mjs [--katex-only]
 */
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { createRequire } from "node:module";

const VENDOR_DIR = join(process.cwd(), "apps/mobile/lib/vendor");
const TMP_DIR = join("/tmp", "recall-vendor-dl");
mkdirSync(VENDOR_DIR, { recursive: true });
mkdirSync(TMP_DIR, { recursive: true });

const mobileRequire = createRequire(join(process.cwd(), "apps/mobile/package.json"));
const katexPackageFile = mobileRequire.resolve("katex/package.json");
const katexPackage = JSON.parse(readFileSync(katexPackageFile, "utf8"));
const VERSIONS = {
  katex: katexPackage.version,
  // Pinned exactly to the committed bundle version (MathJax's internal
  // version is 3.2.1). A floating "3" would silently pull whatever 3.x
  // jsDelivr serves on the next vendor regen. Bump deliberately.
  mermaid: "10",
  vega: "5",
  vegaLite: "5",
  vegaEmbed: "6",
  pdfjs: "3.11.174",
  smilesDrawer: "2.1.7",
};

async function download(url, dest) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`fetch ${url} -> ${res.status}`);
  const buf = Buffer.from(await res.arrayBuffer());
  writeFileSync(dest, buf);
  return buf;
}

/** Each library's file in lib/vendor, by the name the manifest records its hash under. */
const VENDOR_FILES = {
  katexCss: "katex.min.css.txt",
  mermaidMinJs: "mermaid.min.js.txt",
  vegaMinJs: "vega.min.js.txt",
  vegaLiteMinJs: "vega-lite.min.js.txt",
  vegaEmbedMinJs: "vega-embed.min.js.txt",
  pdfMinJs: "pdf.min.js.txt",
  pdfWorkerMinJs: "pdf.worker.min.js.txt",
  smilesDrawerMinJs: "smiles-drawer.min.js.txt",
};

/** Write a library's text as is: the app reads the file, so nothing may wrap it. */
function writeVendorFile(name, content, comment) {
  writeFileSync(join(VENDOR_DIR, VENDOR_FILES[name]), content);
  console.log(`${VENDOR_FILES[name]}: ${comment} ${(content.length / 1024).toFixed(0)} KB`);
}

async function main() {
  // 1. Match CSS and font metrics to the installed KaTeX renderer. A CDN
  // version pin can silently drift from package updates and break layout.
  const katexDist = join(dirname(katexPackageFile), "dist");
  const sourceCss = readFileSync(join(katexDist, "katex.min.css"), "utf8");
  const fonts = new Set();
  const katexCss = sourceCss.replace(/@font-face\{[^}]*\}/g, (rule) => {
    const font = rule.match(/url\(fonts\/([A-Za-z0-9_-]+\.woff2)\)/)?.[1];
    if (!font) throw new Error("KaTeX font face has no supported woff2 source");
    fonts.add(font);
    const data = readFileSync(join(katexDist, "fonts", font)).toString("base64");
    // Replace the entire src declaration, including complete format(...)
    // fallback entries. Removing partial entries used to leave extra ')'.
    return rule.replace(/src:[^;}]+/, `src:url(data:font/woff2;base64,${data}) format("woff2")`);
  });
  if (fonts.size === 0 || /url\(fonts\//.test(katexCss)) {
    throw new Error("KaTeX CSS contains missing or unsupported font sources");
  }
  writeVendorFile("katexCss", katexCss, `KaTeX ${VERSIONS.katex} min CSS with ${fonts.size} woff2 fonts inlined as data URIs.`);

  if (process.argv.includes("--katex-only")) {
    // Preserve every unrelated vendor entry; this path performs no downloads.
    const manifestFile = join(VENDOR_DIR, "manifest.json");
    const manifest = JSON.parse(readFileSync(manifestFile, "utf8"));
    manifest.generatedAt = new Date().toISOString();
    manifest.versions.katex = VERSIONS.katex;
    manifest.sha256.katexCss = sha(katexCss);
    writeFileSync(manifestFile, JSON.stringify(manifest, null, 2) + "\n");
    console.log(`KaTeX ${VERSIONS.katex}: CSS and ${fonts.size} local woff2 fonts regenerated`);
    return;
  }

  // 2. Mermaid
  const mermaidBuf = await download(`https://cdn.jsdelivr.net/npm/mermaid@${VERSIONS.mermaid}/dist/mermaid.min.js`, join(TMP_DIR, "mermaid.min.js"));
  writeVendorFile("mermaidMinJs", mermaidBuf.toString("utf8"), `Mermaid ${VERSIONS.mermaid} min.`);

  // 4. Vega stack
  const vegaBuf = await download(`https://cdn.jsdelivr.net/npm/vega@${VERSIONS.vega}`, join(TMP_DIR, "vega.min.js"));
  writeVendorFile("vegaMinJs", vegaBuf.toString("utf8"), `Vega ${VERSIONS.vega} min.`);
  const vegaLiteBuf = await download(`https://cdn.jsdelivr.net/npm/vega-lite@${VERSIONS.vegaLite}`, join(TMP_DIR, "vega-lite.min.js"));
  writeVendorFile("vegaLiteMinJs", vegaLiteBuf.toString("utf8"), `Vega-Lite ${VERSIONS.vegaLite} min.`);
  const vegaEmbedBuf = await download(`https://cdn.jsdelivr.net/npm/vega-embed@${VERSIONS.vegaEmbed}`, join(TMP_DIR, "vega-embed.min.js"));
  writeVendorFile("vegaEmbedMinJs", vegaEmbedBuf.toString("utf8"), `Vega-Embed ${VERSIONS.vegaEmbed} min.`);

  // 5. pdf.js (main + worker)
  const pdfBase = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${VERSIONS.pdfjs}`;
  const pdfMainBuf = await download(`${pdfBase}/pdf.min.js`, join(TMP_DIR, "pdf.min.js"));
  writeVendorFile("pdfMinJs", pdfMainBuf.toString("utf8"), `pdf.js ${VERSIONS.pdfjs} main.`);
  const pdfWorkerBuf = await download(`${pdfBase}/pdf.worker.min.js`, join(TMP_DIR, "pdf.worker.min.js"));
  writeVendorFile("pdfWorkerMinJs", pdfWorkerBuf.toString("utf8"), `pdf.js ${VERSIONS.pdfjs} worker (loaded via Blob URL at runtime).`);

  // 6. SmilesDrawer (chemistry) — browserify bundle; WebView loads via require(1) shim.
  const smilesUrl =
    `https://cdn.jsdelivr.net/npm/smiles-drawer@${VERSIONS.smilesDrawer}/dist/smiles-drawer.min.js`;
  const smilesBuf = await download(smilesUrl, join(TMP_DIR, "smiles-drawer.min.js"));
  const smilesJs = smilesBuf
    .toString("utf8")
    .replace(/\n?\/\/# sourceMappingURL=.*$/m, "");
  writeVendorFile(
    "smilesDrawerMinJs",
    smilesJs,
    `smiles-drawer ${VERSIONS.smilesDrawer} min (browserify — load via require(1) shim).`,
  );

  // Manifest for traceability
  const allJs = [
    ["mermaidMinJs", mermaidBuf.toString("utf8")],
    ["vegaMinJs", vegaBuf.toString("utf8")],
    ["vegaLiteMinJs", vegaLiteBuf.toString("utf8")],
    ["vegaEmbedMinJs", vegaEmbedBuf.toString("utf8")],
    ["pdfMinJs", pdfMainBuf.toString("utf8")],
    ["pdfWorkerMinJs", pdfWorkerBuf.toString("utf8")],
    ["smilesDrawerMinJs", smilesJs],
  ];
  for (const [name, src] of allJs) {
    if (/<\/script>/i.test(src)) {
      throw new Error(
        `Vendored JS ${name} contains a "</script>" sequence — the inline-` +
        `script rendering path would break. Inspect the upgrade and handle it ` +
        `(e.g. split the sequence) before re-running.`,
      );
    }
  }
  const manifest = {
    generatedAt: new Date().toISOString(),
    versions: VERSIONS,
    sha256: {
      katexCss: sha(katexCss),
      mermaidMinJs: sha(mermaidBuf),
      vegaMinJs: sha(vegaBuf),
      vegaLiteMinJs: sha(vegaLiteBuf),
      vegaEmbedMinJs: sha(vegaEmbedBuf),
      pdfMinJs: sha(pdfMainBuf),
      pdfWorkerMinJs: sha(pdfWorkerBuf),
      smilesDrawerMinJs: sha(smilesJs),
    },
  };
  writeFileSync(join(VENDOR_DIR, "manifest.json"), JSON.stringify(manifest, null, 2) + "\n");
  console.log("Vendor generation complete:", VENDOR_DIR);
}

function sha(buf) {
  return createHash("sha256").update(buf).digest("hex").slice(0, 16);
}

main().catch((e) => { console.error(e); process.exit(1); });
