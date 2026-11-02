/**
 * MathJax-SVG formula rendering — headless via liteAdaptor (no DOM), replacing
 * the retired KaTeX/MathJax WebView path. mathjax-full is CJS and lazy-loaded
 * on the first display formula, so its ~1.5MB parser never touches cold start.
 * Results are LRU-cached by `latex|displayMode` so streaming re-renders of a
 * settled formula are free after first paint.
 *
 * The SVG is self-contained (`fontCache: "none"` inlines every glyph path —
 * no `<use>`/defs for react-native-svg to resolve) and uses `currentColor`;
 * the view substitutes the theme color at render time.
 */
import type { LiteElement } from "mathjax-full/js/adaptors/lite/Element.js";

import { rewriteLatexDialects } from "@/lib/math/latexDialects";

/**
 * Every package but the two that hide a mistake: `noundefined` paints an
 * unknown `\name` in red and `noerrors` paints the source of a formula that
 * failed. Without them the result is an `merror`, which `svgPaintsGlyphs`
 * rejects, and the view falls back to the native renderer.
 */
const HIDDEN_ERROR_PACKAGES = new Set(["noundefined", "noerrors"]);

/** Cap pathological model latex before MathJax can burn the JS thread. */
const MAX_LATEX_CHARS = 4000;
const CACHE_MAX = 200;

export type SvgMathResult = {
  /** Standalone `<svg …>…</svg>` string (mjx-container wrapper stripped). */
  svg: string;
  widthEx: number;
  heightEx: number;
};

/** Renders latex to the container HTML (`<mjx-container><svg…/></mjx-container>`). */
type SvgMathRenderer = (latex: string, display: boolean) => string;

const cache = new Map<string, SvgMathResult | null>();
/**
 * What the view made of a converted formula in each color (`svgMathDrawing`),
 * held by the conversion it was made from: it lives as long as that result.
 */
let drawings = new WeakMap<SvgMathResult, Map<string, unknown>>();
let rendererImpl: SvgMathRenderer | null = null;
let rendererPromise: Promise<SvgMathRenderer> | null = null;

function cacheKey(latex: string, display: boolean): string {
  return `${display ? "d" : "i"}|${latex}`;
}

function cacheGet(key: string): SvgMathResult | null | undefined {
  if (!cache.has(key)) return undefined;
  const value = cache.get(key) ?? null;
  // LRU touch.
  cache.delete(key);
  cache.set(key, value);
  return value;
}

function cacheSet(key: string, value: SvgMathResult | null): void {
  cache.delete(key);
  cache.set(key, value);
  while (cache.size > CACHE_MAX) {
    const oldest = cache.keys().next().value;
    if (oldest === undefined) break;
    cache.delete(oldest);
  }
}

/** Extract the `<svg>…</svg>` from a MathJax mjx-container, dropping the
 * vertical-align style react-native-svg has no use for. */
export function extractSvgElement(containerHtml: string): string | null {
  const start = containerHtml.indexOf("<svg");
  const end = containerHtml.lastIndexOf("</svg>");
  if (start < 0 || end < start) return null;
  const svg = containerHtml.slice(start, end + "</svg>".length);
  const tagEnd = svg.indexOf(">");
  if (tagEnd < 0) return null;
  const openTag = svg
    .slice(0, tagEnd)
    .replace(/ style="[^"]*"/, "");
  return openTag + svg.slice(tagEnd);
}

/**
 * A painted formula has glyph paths. MathJax's error SVG is an `merror` group
 * whose background rect is filled with currentColor — a solid bar once the
 * theme color is substituted. A valid fraction bar is a thin rect without
 * `data-background`. A path-less spacer (`\\`) is the small black square.
 */
export function svgPaintsGlyphs(svg: string): boolean {
  if (svg.includes('data-mml-node="merror"') || svg.includes('data-background="true"')) {
    return false;
  }
  return svg.includes("<path");
}

/**
 * Drop the `ex` width/height. react-native-svg treats those units as pixels
 * and then stretches the drawing to the pixel width and height we pass, so a
 * short formula becomes a bar. `meet` keeps the viewBox aspect.
 */
function svgForDisplay(svg: string): string {
  const tagEnd = svg.indexOf(">");
  if (tagEnd < 0) return svg;
  let open = svg.slice(0, tagEnd).replace(/\s(?:width|height)="[^"]*"/g, "");
  if (!open.includes("preserveAspectRatio=")) {
    open += ' preserveAspectRatio="xMidYMid meet"';
  }
  return open + svg.slice(tagEnd);
}

/** Parse `width="20.765ex"` → 20.765. Linear scan, no regex backtracking. */
export function parseExDimension(svg: string, name: "width" | "height"): number | null {
  const attr = `${name}="`;
  const i = svg.indexOf(attr);
  if (i < 0) return null;
  const rest = svg.slice(i + attr.length);
  const end = rest.indexOf("ex");
  if (end <= 0) return null;
  const value = Number.parseFloat(rest.slice(0, end));
  return Number.isFinite(value) && value > 0 ? value : null;
}

async function loadRenderer(): Promise<SvgMathRenderer> {
  const [mathjaxModule, texModule, svgModule, adaptorModule, handlerModule, allPackages] =
    await Promise.all([
      import("mathjax-full/js/mathjax.js"),
      import("mathjax-full/js/input/tex.js"),
      import("mathjax-full/js/output/svg.js"),
      import("mathjax-full/js/adaptors/liteAdaptor.js"),
      import("mathjax-full/js/handlers/html.js"),
      import("mathjax-full/js/input/tex/AllPackages.js"),
    ]);
  const adaptor = adaptorModule.liteAdaptor();
  handlerModule.RegisterHTMLHandler(adaptor);
  const packages = allPackages.AllPackages.filter((name) => !HIDDEN_ERROR_PACKAGES.has(name));
  const tex = new texModule.TeX({ packages });
  const svgJax = new svgModule.SVG({ fontCache: "none" });
  const doc = mathjaxModule.mathjax.document("", {
    InputJax: tex,
    OutputJax: svgJax,
  });
  return (latex: string, display: boolean) => {
    // With the lite adaptor, a converted formula is a lite DOM element.
    const node = doc.convert(latex, { display }) as LiteElement;
    return adaptor.innerHTML(node);
  };
}

function getRenderer(): Promise<SvgMathRenderer> {
  if (rendererImpl) return Promise.resolve(rendererImpl);
  if (!rendererPromise) {
    rendererPromise = loadRenderer();
    // A failed import must not poison every later formula — allow a retry.
    rendererPromise.catch(() => {
      rendererPromise = null;
    });
  }
  return rendererPromise;
}

/**
 * Load MathJax before the first display formula needs it, so that formula
 * draws at once instead of after the parser loads. A trivial formula runs
 * through it too, so its first real one is not the slow first conversion.
 * Safe to call more than once; a failure is left for the formula to retry.
 */
export function warmSvgMath(): void {
  void getRenderer()
    .then((render) => {
      render("x", true);
    })
    .catch(() => {});
}

/**
 * What `draw` makes of one converted formula in one color (the view parses
 * its SVG into react-native-svg's tree), kept with that conversion so the
 * formula drawn again — a list row reused, a piece of a streaming reply cut
 * off — is not parsed again. Keyed by the result itself, never by a latex
 * string, so a drawing can only ever belong to the formula it was made from.
 * Dropped with the SVG cache.
 */
export function svgMathDrawing<T>(result: SvgMathResult, color: string, draw: () => T): T {
  let byColor = drawings.get(result);
  if (!byColor) {
    byColor = new Map();
    drawings.set(result, byColor);
  }
  if (byColor.has(color)) return byColor.get(color) as T;
  const drawing = draw();
  byColor.set(color, drawing);
  return drawing;
}

/** Cache lookup only: `undefined` = never attempted, `null` = known failure. */
export function peekSvgMath(latex: string, display: boolean): SvgMathResult | null | undefined {
  return cacheGet(cacheKey(latex.trim(), display));
}

/**
 * latex → SVG, or null when the input is empty/pathological or MathJax cannot
 * parse it (callers fall back to the readable native MathText path).
 */
export async function latexToSvgMath(
  latex: string,
  display: boolean,
): Promise<SvgMathResult | null> {
  const trimmed = latex.trim();
  const key = cacheKey(trimmed, display);
  const hit = cacheGet(key);
  if (hit !== undefined) return hit;

  let result: SvgMathResult | null = null;
  if (trimmed && trimmed.length <= MAX_LATEX_CHARS) {
    try {
      const render = await getRenderer();
      const containerHtml = render(rewriteLatexDialects(trimmed), display);
      const svg = extractSvgElement(containerHtml);
      if (svg && svgPaintsGlyphs(svg)) {
        const widthEx = parseExDimension(svg, "width");
        const heightEx = parseExDimension(svg, "height");
        if (widthEx != null && heightEx != null) {
          result = { svg: svgForDisplay(svg), widthEx, heightEx };
        }
      }
    } catch {
      result = null;
    }
  }
  cacheSet(key, result);
  return result;
}

/** Sign-out: the cache holds maths from the previous account's replies. */
export function clearSvgMathCache(): void {
  cache.clear();
  drawings = new WeakMap();
}

/** Test hook: inject a fake renderer (and clear the cache) without mathjax. */
export function setSvgMathRendererForTest(renderer: SvgMathRenderer | null): void {
  rendererImpl = renderer;
  rendererPromise = null;
  cache.clear();
  drawings = new WeakMap();
}
