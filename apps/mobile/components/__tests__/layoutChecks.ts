/**
 * Test helpers over a native math layout tree: the nodes of one kind, and the
 * appearance rules (a bar that outgrows its radicand, a fraction that
 * overlaps, a script left on the baseline) checked without a device screenshot.
 */

import type { MathLayout } from "@/lib/math/layout";

function walkLayout(node: MathLayout, visit: (node: MathLayout) => void): void {
  visit(node);
  for (const child of node.children) walkLayout(child, visit);
}

export function findLayouts(node: MathLayout, kind: MathLayout["kind"]): MathLayout[] {
  const found: MathLayout[] = [];
  walkLayout(node, (item) => {
    if (item.kind === kind) found.push(item);
  });
  return found;
}

/** Layout rules shared by tests and any future debug overlay. */
export function layoutProblems(node: MathLayout, em: number): string[] {
  const problems: string[] = [];
  walkLayout(node, (item) => {
    if (!Number.isFinite(item.width) || !Number.isFinite(item.height)) {
      problems.push(`${item.kind} has a non-finite box`);
    }
    if (item.width < 0 || item.height < 0 || item.outer < 0) {
      problems.push(`${item.kind} has a negative dimension`);
    }
    for (const child of item.children) {
      if (child.width - item.width > 1 && item.kind !== "row") {
        problems.push(`${child.kind} is wider than its ${item.kind} parent`);
      }
    }
    if (item.kind === "sqrt" && item.bodyWidth != null && item.barStart != null && item.barEnd != null) {
      const bar = item.barEnd - item.barStart;
      const extra = bar - item.bodyWidth;
      if (extra < -0.5 || extra > em * 0.28) {
        problems.push(`radical bar ${bar.toFixed(2)} vs radicand ${item.bodyWidth.toFixed(2)}`);
      }
      const strokeEm = item.em && item.em > 0 ? item.em : em;
      if (item.barStart < strokeEm * 0.25) {
        problems.push("radical bar starts inside the hook");
      }
      if (item.index && item.barStart != null) {
        const indexRight = item.index.left + item.index.width;
        if (indexRight > item.barStart + 0.5) {
          problems.push("root index overlaps the radicand");
        }
        const strokeEm = item.em && item.em > 0 ? item.em : em;
        const indexBottom = item.index.top + item.index.lineHeight;
        if (indexBottom < strokeEm * 0.05 - 0.5) {
          problems.push("root index sits above the bar");
        }
      }
    }
    if (item.kind === "frac" && item.contentWidth != null && item.pad != null) {
      if (item.width + 0.01 < item.contentWidth) {
        problems.push("fraction bar shorter than its content");
      }
      if (item.pad > em * 0.5) problems.push("fraction pad is too wide");
      const [num, den] = item.children;
      const head = item.padTop ?? 0;
      const foot = item.padBottom ?? 0;
      if (num && den && item.height + 0.01 < head + num.height + den.height + foot) {
        problems.push("denominator overlaps the fraction bar");
      }
    }
    if (
      item.kind === "accent"
      && (item.accentKind === "overline" || item.accentKind === "underline" || item.spanAccent)
    ) {
      const rule = item.ruleWidth ?? 0;
      const extra = Math.abs(rule - item.inkWidth);
      if (extra > em * 0.2) {
        problems.push(`overline rule ${rule.toFixed(2)} vs ink ${item.inkWidth.toFixed(2)}`);
      }
    }
    if (item.kind === "script" && item.fontSize != null && item.inkWidth > 0) {
      if (item.fontSize > em * 0.8) problems.push("script uses body size");
      if ((item.raise ?? 0) <= 0 && (item.drop ?? 0) <= 0) {
        problems.push("script sits on the baseline");
      }
    }
  });
  return problems;
}
