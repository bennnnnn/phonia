/**
 * mhchem's `\ce{...}` and `\pu{...}` for the native renderer, which has no
 * chemistry typesetter: `\ce{2H2 + O2 -> 2H2O}` becomes upright formulas with
 * lowered counts, raised charges and real arrows. MathJax draws display maths
 * with mhchem itself, so only the inline path takes this rewrite.
 */
import { readGroup } from "@/lib/math/latexGroups";

const ARROWS: Readonly<Record<string, string>> = {
  "->": "\\rightarrow", "<-": "\\leftarrow", "<->": "\\leftrightarrow", "<-->": "\\leftrightarrows",
  "<=>": "\\rightleftharpoons", "<=>>": "\\rightleftharpoons", "<<=>": "\\rightleftharpoons",
};

/** One formula: `Ca(OH)2`, `SO4^2-`, `Na+`, `CuSO4*5H2O`, with a leading count. */
function formula(token: string): string {
  let out = "";
  let i = 0;
  const count = /^\d+(?=[A-Z(\[])/.exec(token)?.[0];
  if (count) {
    out += `${count}\\,`;
    i = count.length;
  }
  while (i < token.length) {
    const rest = token.slice(i);
    const charge = /^\^?\{?([0-9]*[+-])\}?$/.exec(rest) ?? /^\^\{?([0-9]*[+-]?)\}?/.exec(rest);
    if (charge && (rest.startsWith("^") || i > 0)) {
      out += `^{${charge[1]}}`;
      i += charge[0].length;
      continue;
    }
    const digits = /^\d+/.exec(rest)?.[0];
    if (digits) {
      out += `_{${digits}}`;
      i += digits.length;
      continue;
    }
    const hydrate = /^[.*·](\d*)/.exec(rest);
    if (hydrate) {
      out += `\\cdot ${hydrate[1]}`;
      i += hydrate[0].length;
      continue;
    }
    const letters = /^[A-Za-z()[\]]+?(?=\d|[+^.*·-]|$)|^[A-Za-z()[\]]+/.exec(rest)?.[0] ?? rest[0];
    out += /[A-Za-z]/.test(letters) ? `\\mathrm{${letters}}` : letters;
    i += letters.length;
  }
  return out;
}

function chemistryTex(body: string): string {
  return body
    .trim()
    .split(/\s+/)
    .map((token) => {
      if (ARROWS[token]) return ARROWS[token];
      // `->[\Delta]` / `->[above][below]`: the arrow with its condition written over it.
      const labelled = /^(<?[-=]+>{1,2})\[([^\]]*)\](?:\[([^\]]*)\])?$/.exec(token);
      if (labelled && ARROWS[labelled[1]]) {
        const glyph = ARROWS[labelled[1]] === "\\rightleftharpoons" ? "\\xrightleftharpoons" : "\\xrightarrow";
        return `${glyph}[${labelled[3] ?? ""}]{${labelled[2]}}`;
      }
      if (token === "+") return "+";
      if (token === "^") return "\\uparrow";
      if (token === "v") return "\\downarrow";
      // A state or a word ("(aq)", "heat") is written upright as it stands.
      if (/^\((?:s|l|g|aq)\)$/.test(token) || /^[a-z]{2,}$/.test(token)) return `\\mathrm{${token}}`;
      if (token.startsWith("\\") || token.startsWith("$")) return token.replace(/\$/g, "");
      return formula(token);
    })
    .join("\\ ");
}

/** Rewrite every `\ce{...}` and `\pu{...}` in `source`. */
export function rewriteLatexChemistry(source: string): string {
  if (!source.includes("\\ce") && !source.includes("\\pu")) return source;
  let out = "";
  let i = 0;
  while (i < source.length) {
    const command = /^\\(ce|pu)(?![A-Za-z])\s*/.exec(source.slice(i));
    const group = command ? readGroup(source, i + command[0].length) : null;
    if (!command || !group) {
      out += source[i];
      i += 1;
      continue;
    }
    out += `{${command[1] === "ce" ? chemistryTex(group.value) : group.value}}`;
    i = group.next;
  }
  return out;
}
