import { readInlineMathSpan } from "@/lib/markdown/inlineMath";

type RichMathPart = {
  type: "text" | "code" | "math";
  value: string;
  bold?: boolean;
  italic?: boolean;
};

/** Inline rich-body syntax only; never dispatches a nested rich fence. */
export function parseRichMathText(text: string, depth = 0): RichMathPart[] {
  const parts: RichMathPart[] = [];
  let plain = "";
  const flush = () => {
    if (plain) parts.push({ type: "text", value: plain });
    plain = "";
  };
  for (let i = 0; i < text.length;) {
    // Code wins over math, including examples of LaTeX source.
    if (text[i] === "`") {
      let openerEnd = i + 1;
      while (text[openerEnd] === "`") openerEnd += 1;
      const ticks = text.slice(i, openerEnd);
      const end = text.indexOf(ticks, openerEnd);
      if (end >= 0) {
        flush();
        parts.push({ type: "code", value: text.slice(openerEnd, end) });
        i = end + ticks.length;
        continue;
      }
    }
    const math = readInlineMathSpan(text, i, true);
    if (math) {
      flush();
      parts.push({ type: "math", value: math.value });
      i = math.end;
      continue;
    }
    if (text[i] === "*" && depth < 2) {
      const marker = text.startsWith("**", i) ? "**" : "*";
      const end = text.indexOf(marker, i + marker.length);
      if (end > i + marker.length) {
        flush();
        parts.push(...parseRichMathText(text.slice(i + marker.length, end), depth + 1)
          .map((part) => ({ ...part, [marker === "**" ? "bold" : "italic"]: true })));
        i = end + marker.length;
        continue;
      }
    }
    plain += text[i];
    i += 1;
  }
  flush();
  return parts;
}
