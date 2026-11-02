import { looksLikeMarkdownListProse } from "@/lib/markdown/preprocessNormalize";
import { parseFenceLang } from "@/lib/codeHighlight";
import { applyOutsideFences, mapClosedFences, readFenceMarker } from "@/lib/mdFenceScan";

const BLOCK_MATH_RE = /\$\$([\s\S]+?)\$\$/g;
const BLOCK_MATH_BRACKET_RE = /\\\[([\s\S]+?)\\\]/g;
/** Michelin / restaurant price tiers: ($), ($$), ($$$), ($$$$) — not LaTeX. */
const PRICE_TIER_RE = /\(\s*\$+\s*\)/g;
const PRICE_SHIELD_PREFIX = "\uE000P";
const PRICE_SHIELD_SUFFIX = "\uE001";

/** Hide ($$) / ($$$) price markers so block-math regex cannot swallow list prose. */
function shieldPriceTiers(content: string): {
  text: string;
  restore: (s: string) => string;
} {
  const saved: string[] = [];
  const text = content.replace(PRICE_TIER_RE, (match) => {
    const idx = saved.length;
    saved.push(match);
    return `${PRICE_SHIELD_PREFIX}${idx}${PRICE_SHIELD_SUFFIX}`;
  });
  return {
    text,
    restore: (s) =>
      s.replace(
        new RegExp(`${PRICE_SHIELD_PREFIX}(\\d+)${PRICE_SHIELD_SUFFIX}`, "g"),
        (_, index) => saved[Number(index)] ?? "",
      ),
  };
}

export function convertBlockMath(content: string): string {
  const { text: blockMathInput, restore: restorePriceTiers } = shieldPriceTiers(content);
  const blockMathOut = applyOutsideFences(blockMathInput, (prose) => {
    BLOCK_MATH_RE.lastIndex = 0;
    BLOCK_MATH_BRACKET_RE.lastIndex = 0;
    let next = prose.replace(BLOCK_MATH_RE, (_m, latex: string) => {
      return `\n\`\`\`math\n${latex.trim()}\n\`\`\`\n`;
    });
    return next.replace(BLOCK_MATH_BRACKET_RE, (_m, latex: string) => {
      return `\n\`\`\`math\n${latex.trim()}\n\`\`\`\n`;
    });
  });
  return restorePriceTiers(blockMathOut);
}

// A price-tier-split artifact is a stray "$)" (or bare "$") *alone on the
// fence's first line* — not just any body that happens to start with "$".
// A `?` on `)` without also requiring a following newline/end matched any
// legitimate math fence whose body starts with "$" too (e.g. a bare
// equation line normalizeImplicitMath had already wrapped as "$x^2 = 4$"
// before this ran), incorrectly unwrapping real math back to inline text.
const PRICE_TIER_ARTIFACT_LINE_RE = /^\$\)?\s*(?:\n|$)/;
const PRICE_TIER_ARTIFACT_STRIP_RE = /^\$\)?\s*\n?/;

/** Undo mistaken ```math fences that contain markdown lists or price-tier debris. */
export function unwrapCorruptedMathFences(content: string): string {
  return mapClosedFences(content, (info, body, original) => {
    const lang = (info.split(/\s/)[0] ?? "").toLowerCase();
    if (lang !== "math") return original;
    const trimmed = body.trim();
    if (!trimmed) return "";
    if (
      looksLikeMarkdownListProse(trimmed) ||
      PRICE_TIER_ARTIFACT_LINE_RE.test(trimmed) ||
      /^#{1,6}\s/.test(trimmed) ||
      /^\d+\.\s/.test(trimmed) ||
      /Michelin|restaurant|dining|fare|cuisine/i.test(trimmed)
    ) {
      return `\n\n${trimmed.replace(PRICE_TIER_ARTIFACT_STRIP_RE, "")}\n\n`;
    }
    return original;
  });
}

/** Repair list lines truncated by a prior bad ($$) → math-fence split. */
export function repairCorruptedPriceTierMarkdown(content: string): string {
  // A bare or ```math fence whose first line is a stray `$` / `$)`: its rest was the list.
  const out = mapClosedFences(content, (info, body, original) => {
    const lang = parseFenceLang(info);
    const [first = "", ...rest] = body.split("\n");
    if ((lang !== "" && lang !== "math") || !/^\s*\$\)?\s*$/.test(first)) return original;
    const list = rest.join("\n");
    return list.trim() ? `\n\n${list.replace(PRICE_TIER_ARTIFACT_STRIP_RE, "")}\n\n` : "";
  });

  const lines = out.split("\n");
  const fixed: string[] = [];
  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];
    if (/\(\s*$/.test(line) && !/\(\s*\$/.test(line)) {
      const next = lines[i + 1]?.trim() ?? "";
      if (/^\d+\.\s/.test(next) || readFenceMarker(next) != null || next.startsWith("###")) {
        line = line.replace(/\(\s*$/, "($$$)");
      }
    }
    fixed.push(line);
  }
  return fixed.join("\n");
}
